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

/**
 * @namespace Wirecloud.ui
 */
Wirecloud.ui = Wirecloud.ui || {};


(function (ns, se, utils) {

    "use strict";

    const WIRING_CLIPBOARD_STORAGE_KEY = "wirecloud.wiring.clipboard";

    const getClipboardStorage = function getClipboardStorage() {
        try {
            return window.localStorage;
        } catch (e) {
            return null;
        }
    };

    const readCopiedComponents = function readCopiedComponents() {
        const storage = getClipboardStorage();

        if (storage == null) {
            return [];
        }

        try {
            const data = JSON.parse(storage.getItem(WIRING_CLIPBOARD_STORAGE_KEY));

            if (data != null && data.version === 1 && Array.isArray(data.components)) {
                return data.components;
            }
        } catch (e) {
            storage.removeItem(WIRING_CLIPBOARD_STORAGE_KEY);
        }

        return [];
    };

    const writeCopiedComponents = function writeCopiedComponents(components) {
        const storage = getClipboardStorage();

        if (storage == null) {
            return;
        }

        try {
            storage.setItem(WIRING_CLIPBOARD_STORAGE_KEY, JSON.stringify({
                version: 1,
                components: components
            }));
        } catch (e) {
            // Ignore storage quota/private-mode errors. The in-memory clipboard
            // still works for the current page.
        }
    };

    const getCopiedComponentMeta = function getCopiedComponentMeta(copiedComponent) {
        const meta = copiedComponent.meta;
        const metaUri = copiedComponent.metaUri || (meta != null ? meta.uri : null);

        if (meta != null && meta.uri != null) {
            return meta;
        }

        if (metaUri != null && this.workspace != null && this.workspace.resources != null) {
            return this.workspace.resources.getOrCreateMissing(metaUri, copiedComponent.type);
        }

        return meta;
    };

    const bindEndpoint = function bindEndpoint(endpoint) {
        this.connectionEngine.appendEndpoint(endpoint);
        this.suggestionManager.appendEndpoint(endpoint);

        endpoint
            .addEventListener('mouseenter', () => {
                if (!this.connectionEngine.temporalConnection) {
                    this.suggestionManager.showSuggestions(endpoint);
                }
            })
            .addEventListener('mouseleave', () => {
                if (!this.connectionEngine.temporalConnection) {
                    this.suggestionManager.hideSuggestions(endpoint);
                }
            });
    };

    const createAndSetUpBehaviourEngine = function createAndSetUpBehaviourEngine() {
        this.behaviourEngine = new ns.WiringEditor.BehaviourEngine();
        this.behaviourEngine
            .addEventListener('activate', behaviour_onactivate.bind(this))
            .addEventListener('change', behaviour_onchange.bind(this))
            .addEventListener('enable', behaviourengine_onenable.bind(this));

        this.layout.appendChild(this.behaviourEngine)
    };

    const createAndSetUpComponentManager = function createAndSetUpComponentManager() {
        this.componentManager = new ns.WiringEditor.ComponentShowcase();
        this.componentManager.addEventListener('create', (showcase, group, button) => {
            button.disable();

            if (group.meta.type === 'operator') {
                this.workspace.wiring.createOperator(group.meta).then(
                    (operator) => {
                        button.enable();
                        showcase.addComponent(operator);
                    },
                    (error) => {
                        button.enable();
                        (new Wirecloud.ui.MessageWindowMenu(
                            error,
                            Wirecloud.constants.LOGGING.ERROR_MSG
                        )).show();
                    }
                );
            } else {
                this.workspace.view.activeTab.createWidget(group.meta).then(
                    (widgetView) => {
                        button.enable();
                        showcase.addComponent(widgetView.model);
                    },
                    (error) => {
                        button.enable();
                        (new Wirecloud.ui.MessageWindowMenu(
                            error,
                            Wirecloud.constants.LOGGING.ERROR_MSG
                        )).show();
                    }
                );
            }
        });
        this.componentManager.addEventListener('add', (showcase, context) => {
            context.layout = this.layout;
            context.element = this.createComponent(context.component._component, {
                commit: false
            });
        });
        this.layout.appendChild(this.componentManager);
    };

    const createAndSetUpConnectionEngine = function createAndSetUpConnectionEngine() {
        this.connectionEngine = new ns.WiringEditor.ConnectionEngine(this.layout.content, findWiringEngine.bind(this));
        this.connectionEngine
            .addEventListener('click', connection_onclick.bind(this))
            .addEventListener('dragstart', connection_ondragstart.bind(this))
            .addEventListener('dragend', connection_ondragend.bind(this))
            .addEventListener('establish', connection_onestablish.bind(this))
            .addEventListener('duplicate', connection_onduplicate.bind(this));

        return this;
    };

    const findWiringEngine = function findWiringEngine() {
        return this.workspace.wiring;
    };

    const createAndSetUpLayout = function createAndSetUpLayout() {
        const centerContainer = new se.Container({ class: 'se-vl-center-container' });
        const southContainer = new se.Container({ class: 'se-vl-south-container' });

        this.layout = new se.OffCanvasLayout();
        this.layout.sidebar.addClassName("wiring-sidebar");
        this.layout.content.addClassName("wiring-diagram");

        setUpNavbarView.call(this);

        this.wrapperElement.classList.add('se-vertical-layout');
        this.appendChild(centerContainer);
        this.appendChild(southContainer);

        this.initialMessage = createInitialMessage();
        this.layout.content.appendChild(this.initialMessage);

        this.layout
            .addEventListener('slideOut', () => {
                this.btnFindComponents.active = false;
                this.btnListBehaviours.active = false;
                this.behaviourEngine.stopOrdering();
            })
            .addEventListener('slideIn', (offcanvas, panel) => {
                this.btnFindComponents.active = panel.hasClassName("we-panel-components");
                this.btnListBehaviours.active = panel.hasClassName("we-panel-behaviours");

                if (this.btnFindComponents.active) {
                    this.behaviourEngine.stopOrdering();
                }
            });

        this.legend = {
            title: document.createElement('span'),
            connections: document.createElement('span'),
            operators: document.createElement('span'),
            widgets: document.createElement('span')
        };
        this.legend.title.setAttribute('aria-live', 'polite');
        this.legend.connections.setAttribute('aria-live', 'polite');
        this.legend.operators.setAttribute('aria-live', 'polite');
        this.legend.widgets.setAttribute('aria-live', 'polite');
        Object.freeze(this.legend);

        Wirecloud.addEventListener('loaded', () => {
            southContainer.appendChild((new se.GUIBuilder()).parse(Wirecloud.currentTheme.templates['wirecloud/wiring/footer'], {
                title: this.legend.title,
                connections: this.legend.connections,
                operators: this.legend.operators,
                widgets: this.legend.widgets
            }).children[1]);
        });

        this.layout.content.get().addEventListener('dblclick', layout_ondblclick.bind(this));
        this._layout_onclick = layout_onclick.bind(this);
        this.layout.content.get().addEventListener('click', this._layout_onclick);

        centerContainer.appendChild(this.layout);
    };

    const createInitialMessage = function createInitialMessage() {
        const alert = new se.Alert({
            title: utils.gettext("Hello, welcome to the Wiring Editor view!"),
            message: utils.gettext("In this view you can connect all the components of your dashboard in a visual way."),
            state: 'info',
            alignment: 'static-top'
        });

        alert.heading.addClassName('text-center');
        alert.addNote(new StyledElements.Fragment(utils.gettext("Open the sidebar using the <em>Find components</em> button and drag &amp; drop components (operators/widgets) from the sidebar for being able to connect them as you wish.")));

        return alert;
    };

    const setUpNavbarView = function setUpNavbarView() {
        this.btnFindComponents = new se.ToggleButton({
            title: utils.gettext("Find components"),
            class: "we-show-component-sidebar-button",
            iconClass: "fas fa-archive",
            stackedIconClass: "fas fa-plus-circle"
        });
        this.btnFindComponents.addEventListener('click', function (button) {
            if (button.active) {
                this.componentManager.searchComponents.refresh();
            }
            showSelectedPanel.call(this, button, 1);
        }.bind(this));

        this.btnListBehaviours = new se.ToggleButton({
            title: utils.gettext("List behaviours"),
            class: "we-show-behaviour-sidebar-button",
            iconClass: "fas fa-sitemap"
        });
        this.btnListBehaviours.addEventListener('click', function (button) {
            showSelectedPanel.call(this, button, 0);
        }.bind(this));

        return this;
    };

    const disableComponent = function disableComponent(component) {
        const item = this.componentManager.findComponent(component.type, component.id);

        if (item != null) {
            item.used = true;
        }

        return this;
    };

    const readyView = function readyView() {
        this.layout.slideOut();

        this.behaviourEngine.clear();
        this.componentManager.clear();
        this.suggestionManager.enable();

        this.orderableComponent = null;
    };

    const loadWiringStatus = function loadWiringStatus() {
        const wiringEngine = this.workspace.wiring;
        const visualStatus = wiringEngine.visualdescription;

        // Loading the widgets used in this workspace...
        loadComponents.call(this, this.workspace.widgets, visualStatus.components.widget);
        // ...completed.

        // Loading the operators used in this workspace...
        loadComponents.call(this, wiringEngine.operators, visualStatus.components.operator);
        // ...completed.

        // Loading the connections established in the workspace...
        loadConnections.call(this, wiringEngine.connections, visualStatus.connections);
        // ...completed.

        this.behaviourEngine.loadBehaviours(visualStatus.behaviours);
    };

    const loadConnections = function loadConnections(connections, vInfo) {
        connections.forEach(function (connection) {
            let i;

            if (connection.volatile) {
                return;
            }

            const source = findEndpoint.call(this, 'source', connection.source);
            const target = findEndpoint.call(this, 'target', connection.target);
            const options = {};

            for (i = vInfo.length - 1; i >= 0; i--) {
                if (connection.source.id === vInfo[i].sourcename && connection.target.id === vInfo[i].targetname) {
                    options.sourceHandle = vInfo[i].sourcehandle;
                    options.targetHandle = vInfo[i].targethandle;
                    vInfo.splice(i, 1);
                    break;
                }
            }

            this.connectionEngine.connect(connection, source, target, options);
        }, this);
    };

    const loadComponents = function loadComponents(components, visualInfo) {
        components.forEach(function (component) {
            this.componentManager.addComponent(component);

            if (component.id in visualInfo) {
                this.createComponent(component, visualInfo[component.id]);
            }
        }, this);
    };

    const component_onendpointadded = function component_onendpointadded(component, endpoint) {
        bindEndpoint.call(this, endpoint);
    };

    const component_onendpointremoved = function component_onendpointremoved(component, endpoint) {
        this.connectionEngine.removeEndpoint(endpoint);
        this.suggestionManager.removeEndpoint(endpoint);
    };

    const findEndpoint = function findEndpoint(rol, endpoint) {
        let component;

        component = this.behaviourEngine.components[endpoint.component.meta.type][endpoint.component.id];

        if (!component) {
            component = this.componentManager.findComponent(endpoint.component.meta.type, endpoint.component.id);
            component = this.createComponent(component._component);
        }

        return component.getEndpoint(rol, endpoint.name);
    };

    const clearComponentSelection = function clearComponentSelection() {
        let type, id, component;

        for (type in this.selectedComponents) {
            for (id in this.selectedComponents[type]) {
                component = this.selectedComponents[type][id];
                component.setUp();
                delete component.initialPosition;
                delete this.selectedComponents[type][id];
            }
        }

        this.selectedCount = 0;
    };

    const document_onkeydown = function document_onkeydown(key, modifiers) {
        switch (key) {
        case 'Backspace':
        case 'Delete':
            const componentsToRemove = [];

            if (hasSelectedComponents.call(this)) {
                for (const type in this.selectedComponents) {
                    for (const id in this.selectedComponents[type]) {
                        const component = this.selectedComponents[type][id];

                        if (component.isRemovable()) {
                            componentsToRemove.push(component);
                        }
                    }
                }

                if (componentsToRemove.length) {
                    this.behaviourEngine.removeComponentList(componentsToRemove);
                    clearComponentSelection.call(this);
                }
            }

            return true;
        case 'c':
            if (modifiers.ctrlKey || modifiers.metaKey) {
                copyComponents.call(this);
                return true;
            }
            break;
        case 'v':
            if (modifiers.ctrlKey || modifiers.metaKey) {
                pasteComponents.call(this);
                return true;
            }
            break;
        }
    };

    const hasSelectedComponents = function hasSelectedComponents() {
        return Object.keys(this.selectedComponents.operator).length > 0 || Object.keys(this.selectedComponents.widget).length > 0;
    };

    const behaviourengine_onenable = function behaviourengine_onenable(behaviourEngine, enabled) {
        this.connectionEngine.forEachConnection((connection) => {
            connection.removeAllowed = true;
            connection.background = false;
            this.behaviourEngine.updateConnection(connection);
        });

        this.behaviourEngine.forEachComponent((component) => {
            component.removeCascadeAllowed = enabled;
            component.removeAllowed = true;
            component.background = false;
            this.behaviourEngine.updateComponent(component);
        });
    };

    const behaviour_onactivate = function behaviour_onactivate(behaviourEngine, behaviour, viewpoint) {
        const currentStatus = behaviour.getCurrentStatus();

        switch (viewpoint) {
        case ns.WiringEditor.BehaviourEngine.GLOBAL:

            this.connectionEngine.forEachConnection(function (connection) {
                connection.removeAllowed = (behaviourEngine.filterByConnection(connection).length === 1);
                connection.show().background = !behaviour.hasConnection(connection);
            });

            this.behaviourEngine.forEachComponent(function (component) {
                component.removeAllowed = (behaviourEngine.filterByComponent(component).length === 1);
                component.removeCascadeAllowed = true;
                component.background = !behaviour.hasComponent(component);
            });

            break;
        }

        behaviour_onchange.call(this, behaviourEngine, currentStatus, true);
    };

    const connection_onduplicate = function connection_onduplicate(connectionEngine, connection, connectionBackup) {
        if (connection.background) {
            this.behaviourEngine.updateConnection(connection, true);

            if (connectionBackup != null) {
                removeBackupConnection.call(this, connectionBackup);
            }
        }
    };

    const connection_onestablish = function connection_onestablish(connectionEngine, connection, connectionBackup) {
        this.behaviourEngine.updateConnection(connection);

        connection
            .addEventListener('change', () => {
                this.behaviourEngine.updateConnection(connection);
            })
            .addEventListener('optremove', () => {
                this.behaviourEngine.removeConnection(connection);
            })
            .addEventListener('optshare', () => {
                this.behaviourEngine.updateConnection(connection, true);
            });

        if (connectionBackup != null) {
            removeBackupConnection.call(this, connectionBackup);
        }
    };

    const removeBackupConnection = function removeBackupConnection(connection) {
        this.behaviourEngine.removeConnection(connection);

        if (this.behaviourEngine.hasConnection(connection)) {
            showConnectionChangeModal.call(this, connection);
        }
    };

    const showConnectionChangeModal = function showConnectionChangeModal(connection) {
        const builder = new se.GUIBuilder();

        const message = builder.parse(builder.DEFAULT_OPENING + utils.gettext("The connection will also be modified for the rest of behaviours, would you like to continue?") + builder.DEFAULT_CLOSING);

        const modal = new Wirecloud.ui.AlertWindowMenu(message);
        modal.setHandler(() => {
            this.behaviourEngine.removeConnection(connection, true);
        }).show();
    };

    const component_onremove = function component_onremove(component) {
        component.forEachEndpoint(function (endpoint) {
            this.connectionEngine.removeEndpoint(endpoint);
            this.suggestionManager.removeEndpoint(endpoint);
        }.bind(this));

        if (component.id in this.selectedComponents[component.type]) {
            delete this.selectedComponents[component.type][component.id];
            this.selectedCount--;
        }

        if (component.missing) {
            this.componentManager.removeComponent(component._component);
        } else {
            this.componentManager.findComponent(component.type, component.id).used = false;
        }

        if (!this.behaviourEngine.hasComponents()) {
            this.initialMessage.show();
        }
    };

    const connection_onclick = function connection_onclick(connectionEngine, connectionClicked) {
        clearComponentSelection.call(this);

        if (this.orderableComponent != null) {
            this.orderableComponent.setUp();
            this.orderableComponent = null;
        }
    };

    const connection_ondragstart = function connection_ondragstart(connectionEngine, connection, initialEndpoint, realEndpoint) {
        this.collapsedComponents = [];

        this.behaviourEngine.forEachComponent((component) => {
            if (component.collapsed) {
                component.collapsed = false;
                this.collapsedComponents.push(component);
            }
        });

        if (this.connectionEngine._connectionBackup != null) {
            this.suggestionManager.hideSuggestions(realEndpoint);
            this.suggestionManager.showSuggestions(initialEndpoint);
        }

        this.layout.content.get().removeEventListener('click', this._layout_onclick);
    };

    const connection_ondragend = function connection_ondragend(connectionEngine, connection, initialEndpoint) {
        if (this.collapsedComponents != null) {

            this.collapsedComponents.forEach((component) => {
                component.collapsed = true;
            });

            delete this.collapsedComponents;
        }

        this.suggestionManager.hideSuggestions(initialEndpoint);

        setTimeout(() => {
            this.layout.content.get().addEventListener('click', this._layout_onclick);
        }, 0);
    };

    const behaviour_onchange = function behaviour_onchange(behaviourEngine, currentStatus, enabled) {
        if (enabled) {
            currentStatus.title = "<strong>" + utils.gettext("Behaviour") + ":</strong> " + currentStatus.title;
        }

        this.legend.title.innerHTML = currentStatus.title;
        this.legend.connections.textContent = currentStatus.connections;
        this.legend.operators.textContent = currentStatus.components.operator;
        this.legend.widgets.textContent = currentStatus.components.widget;
    };

    const layout_onclick = function layout_onclick() {
        clearComponentSelection.call(this);

        if (this.orderableComponent != null) {
            this.orderableComponent.setUp();
            this.orderableComponent = null;
        }

        this.connectionEngine.setUp();
    };

    const layout_ondblclick = function layout_ondblclick(event) {
        event.preventDefault();
        this.layout.slideOut();
    };

    const showSelectedPanel = function showSelectedPanel(button, panelIndex) {
        if (button.active) {
            this.layout.slideIn(panelIndex);
        } else {
            this.layout.slideOut();
        }
    };

    const component_onclick = function component_onclick(component, event) {
        let type, id;

        if (!component.active && component.id in this.selectedComponents[component.type]) {
            if (event.ctrlKey || event.metaKey) {
                delete component.initialPosition;
                delete this.selectedComponents[component.type][component.id];
                this.selectedCount--;
            } else {
                if (this.selectedCount > 1) {
                    for (type in this.selectedComponents) {
                        for (id in this.selectedComponents[type]) {
                            this.selectedComponents[type][id].active = false;
                            delete this.selectedComponents[type][id].initialPosition;
                            delete this.selectedComponents[type][id];
                        }
                    }
                    this.selectedCount = 0;
                    component.active = true;
                } else {
                    delete component.initialPosition;
                    delete this.selectedComponents[component.type][component.id];
                    this.selectedCount = 0;
                }
            }
        }

        if (component.active && !(component.id in this.selectedComponents[component.type])) {
            this.selectedComponents[component.type][component.id] = component;
            this.selectedCount++;
        }
    };

    const component_ondragstart = function component_ondragstart(component, event) {
        let type, id, selectedComponent;

        if (this.orderableComponent != null) {
            this.orderableComponent.setUp();
            this.orderableComponent = null;
        }

        this.connectionEngine.setUp();

        if (event.ctrlKey || event.metaKey) {
            if (!(component.id in this.selectedComponents[component.type])) {
                this.selectedComponents[component.type][component.id] = component;
                this.selectedCount++;
            }
        } else if (!(component.id in this.selectedComponents[component.type])) {
            for (type in this.selectedComponents) {
                for (id in this.selectedComponents[type]) {
                    this.selectedComponents[type][id].active = false;
                    delete this.selectedComponents[type][id].initialPosition;
                    delete this.selectedComponents[type][id];
                }
            }
            this.selectedCount = 0;
        }

        if (component.id in this.selectedComponents[component.type]) {
            for (type in this.selectedComponents) {
                for (id in this.selectedComponents[type]) {
                    selectedComponent = this.selectedComponents[type][id];
                    selectedComponent.initialPosition = selectedComponent.position();
                }
            }
        }
    };

    const component_ondrag = function component_ondrag(component, x, y) {
        let type, id, selectedComponent;

        for (type in this.selectedComponents) {
            for (id in this.selectedComponents[type]) {
                if (component.type !== type || component.id !== id) {
                    selectedComponent = this.selectedComponents[type][id];
                    selectedComponent.position({
                        x: selectedComponent.initialPosition.x + x,
                        y: selectedComponent.initialPosition.y + y
                    });
                }
            }
        }
    };

    const component_ondragend = function component_ondragend(component) {
        let type, id, selectedComponent;

        for (type in this.selectedComponents) {
            for (id in this.selectedComponents[type]) {
                selectedComponent = this.selectedComponents[type][id];
                selectedComponent.active = true;

                if (component.type !== type || component.id !== id) {
                    selectedComponent.dispatchEvent('change', {position: selectedComponent.position()});
                }
            }
        }
    };

    const component_onorderstart = function component_onorderstart(component) {
        if (this.orderableComponent != null && !this.orderableComponent.equals(component)) {
            this.orderableComponent.setUp();
        }

        this.orderableComponent = component;
        this.connectionEngine.enabled = false;
        this.suggestionManager.disable();

        this.layout.content.get().removeEventListener('click', this._layout_onclick);
    };

    const component_onorderend = function component_onorderend(component) {
        this.orderableComponent = null;
        this.connectionEngine.enabled = true;
        this.suggestionManager.enable();

        setTimeout(() => {
            this.layout.content.get().addEventListener('click', this._layout_onclick);
        }, 0);
    };

    const copyComponents = function copyComponents() {
        this.copiedComponents = [];
        const allConnections = [];

        // Second pass: collect all connections between selected components
        for (const type in this.selectedComponents) {
            for (const id in this.selectedComponents[type]) {
                const component = this.selectedComponents[type][id];

                // Check all endpoints of this component
                component.forEachEndpoint((endpoint) => {
                    if (!endpoint.connections) {
                        return;
                    }

                    endpoint.connections.forEach((connection) => {
                        const sourceEndpointId = connection.source && connection.source.endpoint ? connection.source.endpoint.id : null;
                        const targetEndpointId = connection.target && connection.target.endpoint ? connection.target.endpoint.id : null;

                        if (!sourceEndpointId || !targetEndpointId) {
                            return;
                        }

                        const sourceComponent = connection.source && connection.source.endpoint ? connection.source.endpoint.component : null;
                        const targetComponent = connection.target && connection.target.endpoint ? connection.target.endpoint.component : null;

                        // Only include connections where BOTH endpoints are in selected components
                        if (sourceComponent && targetComponent &&
                            sourceComponent.id in this.selectedComponents[sourceComponent.type] &&
                            targetComponent.id in this.selectedComponents[targetComponent.type]) {

                            const connectionKey = `${sourceEndpointId}|${targetEndpointId}`;

                            // Check if we already have this connection
                            if (!allConnections.some(c => c.key === connectionKey)) {
                                allConnections.push({
                                    key: connectionKey,
                                    sourceComponentId: sourceComponent.id,
                                    sourceComponentType: sourceComponent.type,
                                    sourceEndpointName: connection.source.endpoint.name,
                                    sourceEndpointId: sourceEndpointId,
                                    targetComponentId: targetComponent.id,
                                    targetComponentType: targetComponent.type,
                                    targetEndpointName: connection.target.endpoint.name,
                                    targetEndpointId: targetEndpointId,
                                    sourceHandle: connection.sourceHandle,
                                    targetHandle: connection.targetHandle
                                });
                            }
                        }
                    });
                });
            }
        }

        // Third pass: copy component information with connections
        for (const type in this.selectedComponents) {
            for (const id in this.selectedComponents[type]) {
                const component = this.selectedComponents[type][id];
                const sourceEndpoints = [];

                // Copy preferences as simple key-value pairs
                const preferences = {};
                for (const key in component._component.preferences) {
                    preferences[key] = component._component.preferences[key].value;
                }

                // Copy properties as simple key-value pairs
                const properties = {};
                for (const key in component._component.properties) {
                    properties[key] = component._component.properties[key].value;
                }

                // Build source endpoints with connections for this component
                component.forEachEndpoint((endpoint) => {
                    if (endpoint.type === 'source') {
                        const endpointInfo = {
                            name: endpoint.name,
                            connections: []
                        };

                        // Find connections that originate from this endpoint
                        allConnections.forEach((conn) => {
                            if (conn.sourceComponentId === component.id && conn.sourceEndpointName === endpoint.name) {
                                endpointInfo.connections.push({
                                    sourceEndpoint: conn.sourceEndpointName,
                                    targetComponent: conn.targetComponentId,
                                    targetComponentType: conn.targetComponentType,
                                    targetEndpoint: conn.targetEndpointName,
                                    sourceHandle: conn.sourceHandle,
                                    targetHandle: conn.targetHandle
                                });
                            }
                        });

                        sourceEndpoints.push(endpointInfo);
                    }
                });

                this.copiedComponents.push({
                    id: component.id,
                    type: component.type,
                    meta: component._component.meta,
                    metaUri: component._component.meta.uri,
                    position: component.position(),
                    collapsed: component.collapsed,
                    preferences: preferences,
                    properties: properties,
                    permissions: component._component.permissions,
                    sourceEndpoints: sourceEndpoints,
                });
            }
        }
        // Copy operation completed
        writeCopiedComponents(this.copiedComponents);
    };

    const pasteComponents = function pasteComponents() {
        const copiedComponents = this.copiedComponents.length > 0 ? this.copiedComponents : readCopiedComponents();

        if (!copiedComponents || copiedComponents.length === 0) {
            return;
        }

        this.copiedComponents = copiedComponents;

        const newComponents = {};

        (async () => {
            const pasteOffset = 20;

            for (const copiedComponent of copiedComponents) {
                const copiedComponentMeta = getCopiedComponentMeta.call(this, copiedComponent);

                if (copiedComponentMeta == null) {
                    continue;
                }

                if (copiedComponent.type === 'operator') {
                    const operatorOptions = {
                        position: {
                            x: copiedComponent.position.x + pasteOffset,
                            y: copiedComponent.position.y + pasteOffset
                        },
                        collapsed: copiedComponent.collapsed
                    };

                    operatorOptions.preferences = {};
                    for (const key in copiedComponent.preferences) {
                        operatorOptions.preferences[key] = {
                            value: copiedComponent.preferences[key]
                        };
                    }
                    operatorOptions.properties = {};
                    for (const key in copiedComponent.properties) {
                        operatorOptions.properties[key] = {
                            value: copiedComponent.properties[key]
                        };
                    }

                    const newComponent = await this.workspace.wiring.createOperator(copiedComponentMeta, operatorOptions);
                    const visualOptions = {
                        position: operatorOptions.position,
                        collapsed: operatorOptions.collapsed,
                        commit: false
                    };

                    const component = this.createComponent(newComponent, visualOptions);
                    newComponents[copiedComponent.id] = component;
                    this.componentManager.addComponent(newComponent);
                    this.layout.content.appendChild(component);
                    this.behaviourEngine.updateComponent(component);
                    disableComponent.call(this, component);

                } else if (copiedComponent.type === 'widget') {
                    try {
                        const widgetView = await this.workspace.view.activeTab.createWidget(copiedComponentMeta);

                        // Apply preferences AFTER widget is created
                        for (const key in copiedComponent.preferences) {
                            const prefValue = copiedComponent.preferences[key];
                            if (widgetView.model.preferences && widgetView.model.preferences[key]) {
                                widgetView.model.preferences[key].value = prefValue;
                            }
                        }

                        // Apply properties
                        for (const key in copiedComponent.properties) {
                            const propValue = copiedComponent.properties[key];
                            if (widgetView.model.properties && widgetView.model.properties[key]) {
                                widgetView.model.properties[key].value = propValue;
                            }
                        }

                        const visualOptions = {
                            position: {
                                x: copiedComponent.position.x + pasteOffset,
                                y: copiedComponent.position.y + pasteOffset
                            },
                            collapsed: copiedComponent.collapsed,
                            commit: true
                        };

                        const component = this.createComponent(widgetView.model, visualOptions);
                        newComponents[copiedComponent.id] = component;
                        this.componentManager.addComponent(widgetView.model);
                        this.layout.content.appendChild(component);
                        this.behaviourEngine.updateComponent(component);
                        disableComponent.call(this, component);
                    } catch (error) {
                        console.error('Widget creation error:', error);
                    }
                }
            }

            for (const copiedComponent of copiedComponents) {
                const newComponent = newComponents[copiedComponent.id];
                if (!newComponent) {
                    continue;
                }

                for (const endpointInfo of copiedComponent.sourceEndpoints) {
                    const sourceEndpoint = newComponent.getEndpoint('source', endpointInfo.name);
                    if (!sourceEndpoint) {
                        continue;
                    }

                    for (const connectionInfo of endpointInfo.connections) {
                        const targetComponent = newComponents[connectionInfo.targetComponent];
                        if (!targetComponent) {
                            continue;
                        }

                        const targetEndpoint = targetComponent.getEndpoint('target', connectionInfo.targetEndpoint);
                        if (!targetEndpoint) {
                            continue;
                        }

                        try {
                            const connection = await this.workspace.wiring.createConnection(sourceEndpoint._endpoint, targetEndpoint._endpoint);
                            this.connectionEngine.connect(connection, sourceEndpoint, targetEndpoint, {
                                sourceHandle: connectionInfo.sourceHandle,
                                targetHandle: connectionInfo.targetHandle
                            });
                        } catch (error) {
                            console.error('Failed to create connection:', error);
                        }
                    }
                }
            }

            clearComponentSelection.call(this);
            for (const id in newComponents) {
                const newComponent = newComponents[id];
                newComponent.active = true;
                this.selectedComponents[newComponent.type][newComponent.id] = newComponent;
                this.selectedCount++;
                newComponent.toFirst();
            }
        })().catch((error) => {
            console.error('Error in paste operation:', error);
        });
    };

    /**
     * Creates a new wiring editor usable for adding operators, creating and
     * remove connections, ...
     *
     * @name Wirecloud.ui.WiringEditor
     * @extends {StyledElements.Alternative}
     *
     * @constructor
     *
     * @param {Number} id
     *      StyledElements.Alternative id
     * @param {PlainObject} [options]
     *      Options for initializing this WiringEditor
     */
    ns.WiringEditor = class WiringEditor extends se.Alternative {

        constructor(id, options) {
            options = utils.merge({}, options);
            options.class = "wc-workspace-wiring";

            super(id, options);

            createAndSetUpLayout.call(this);

            Wirecloud.addEventListener('loaded', createAndSetUpBehaviourEngine.bind(this));
            Wirecloud.addEventListener('loaded', createAndSetUpComponentManager.bind(this));
            createAndSetUpConnectionEngine.call(this);

            this.suggestionManager = new ns.WiringEditor.KeywordSuggestion();

            this.selectedComponents = { operator: {}, widget: {} };
            this.selectedCount = 0;

            this.orderableComponent = null;
            this.copiedComponents = readCopiedComponents();
            this.disable();
        }

        /**
         * @override
         */
        _onhidden(hidden) {

            super._onhidden(hidden);

            if (hidden) {
                this.unload();
            } else {
                this.load(Wirecloud.activeWorkspace);
            }

        }

        /**
         * [TODO: createComponent description]
         *
         * @param {Wiring.Component} wiringComponent
         *      [TODO: description]
         * @param {PlainObject} [options]
         *      [TODO: description]
         * @returns {ComponentDraggable}
         *      [description]
         */
        createComponent(wiringComponent, options) {
            options = utils.merge({ commit: true, removecascade_allowed: this.behaviourEngine.enabled }, options);

            const ComponentDraggable = (ns.registry != null) ? ns.registry.get('WiringEditor.ComponentDraggable', ns.WiringEditor.ComponentDraggable) : ns.WiringEditor.ComponentDraggable;
            const component = new ComponentDraggable(wiringComponent, options);
            component
                .addEventListener('endpointadded', component_onendpointadded.bind(this))
                .addEventListener('endpointremoved', component_onendpointremoved.bind(this))
                .addEventListener('change', () => {
                    this.behaviourEngine.updateComponent(component);
                })
                .addEventListener('click', component_onclick.bind(this))
                .addEventListener('dragstart', component_ondragstart.bind(this))
                .addEventListener('drag', component_ondrag.bind(this))
                .addEventListener('dragend', component_ondragend.bind(this))
                .addEventListener('orderstart', component_onorderstart.bind(this))
                .addEventListener('orderend', component_onorderend.bind(this))
                .addEventListener('optremove', () => {
                    this.behaviourEngine.removeComponent(component);
                })
                .addEventListener('optremovecascade', () => {
                    this.behaviourEngine.removeComponent(component, true);
                })
                .addEventListener('optshare', () => {
                    this.behaviourEngine.updateComponent(component, true);
                })
                .addEventListener('remove', component_onremove.bind(this));

            component.forEachEndpoint(bindEndpoint.bind(this));
            this.initialMessage.hide();

            if (options.commit) {
                this.layout.content.appendChild(component);
                this.behaviourEngine.updateComponent(component);
                disableComponent.call(this, component);
            }

            return component;
        }

        buildStateData() {
            const currentState = Wirecloud.HistoryManager.getCurrentState();
            return {
                workspace_owner: currentState.workspace_owner,
                workspace_name: currentState.workspace_name,
                view: this.view_name,
                params: currentState.params
            };
        }

        getBreadcrumb() {
            const workspace_breadcrum = Wirecloud.UserInterfaceManager.views.workspace.getBreadcrumb();

            for (let i = 0; i < workspace_breadcrum.length; i += 1) {
                delete workspace_breadcrum[i].menu;
            }

            workspace_breadcrum.push({
                label: this.view_name
            });

            return workspace_breadcrum;
        }

        getTitle() {
            return utils.interpolate(utils.gettext("%(workspace_title)s - Wiring"), {
                workspace_title: Wirecloud.UserInterfaceManager.views.workspace.getTitle()
            });
        }

        getToolbarButtons() {
            return [this.btnFindComponents, this.btnListBehaviours];
        }

        /**
         * Modes available from this view (see
         * {Wirecloud.ui.WorkspaceView#getModes}).
         *
         * @returns {Array.<Object>}
         */
        getModes() {
            const switchToWorkspace = (editing) => {
                const workspaceView = Wirecloud.UserInterfaceManager.views.workspace;
                Wirecloud.UserInterfaceManager.changeCurrentView('workspace');
                if (typeof workspaceView.setEditing === 'function') {
                    workspaceView.setEditing(editing);
                }
            };

            return [
                {
                    id: 'view',
                    label: utils.gettext('View'),
                    icon: 'fas fa-eye',
                    shortcut: 'v',
                    active: false,
                    enabled: true,
                    activate: () => switchToWorkspace(false)
                },
                {
                    id: 'edit',
                    label: utils.gettext('Edit'),
                    icon: 'fas fa-pencil-alt',
                    shortcut: 'e',
                    active: false,
                    enabled: true,
                    activate: () => switchToWorkspace(true)
                },
                {
                    id: 'wiring',
                    label: utils.gettext('Wiring'),
                    icon: 'fas fa-sitemap',
                    shortcut: 'w',
                    active: true,
                    enabled: true,
                    activate: () => {}
                }
            ];
        }

        /**
         * Main action of the wiring editor: adding operators.
         *
         * @returns {Object}
         */
        getPrimaryAction() {
            return {
                id: 'add-operator',
                label: utils.gettext('Add operator'),
                icon: 'fas fa-plus',
                enabled: this.btnFindComponents.enabled,
                run: () => {
                    if (!this.btnFindComponents.active) {
                        this.btnFindComponents.click();
                    }
                }
            };
        }

        /**
         * @returns {Array.<Object>}
         */
        getSecondaryActions() {
            return [
                {
                    id: 'behaviours',
                    label: utils.gettext('Behaviours'),
                    icon: 'fas fa-sitemap',
                    enabled: this.btnListBehaviours.enabled,
                    active: this.btnListBehaviours.active,
                    run: () => {
                        this.btnListBehaviours.click();
                    }
                }
            ];
        }

        /**
         * Removes the selected components or, if there is no selected
         * component, the active connection.
         *
         * @returns {Boolean} `true` if something was removed
         */
        deleteSelection() {
            if (hasSelectedComponents.call(this)) {
                document_onkeydown.call(this, 'Delete', {});
                return true;
            }

            const connection = this.connectionEngine.activeConnection;
            if (connection != null && !connection.readonly && connection.btnRemove.enabled) {
                connection.btnRemove.click();
                return true;
            }

            return false;
        }

        /**
         * Cancels the current interaction: closes the sidebar, deselects the
         * components or deactivates the active connection.
         *
         * @returns {Boolean} `true` if there was something to cancel
         */
        cancel() {
            if (this.connectionEngine.cancelTemporalConnection()) {
                return true;
            } else if (this.btnFindComponents.active || this.btnListBehaviours.active) {
                (this.btnFindComponents.active ? this.btnFindComponents : this.btnListBehaviours).click();
                return true;
            } else if (hasSelectedComponents.call(this)) {
                clearComponentSelection.call(this);
                return true;
            } else if (this.connectionEngine.hasActiveConnection()) {
                this.connectionEngine.activeConnection.click();
                return true;
            }
            return false;
        }

        goUp() {
            Wirecloud.UserInterfaceManager.changeCurrentView('workspace');
        }

        /**
         * Reads wiring configuration from the given workspace and prepares the
         * user interface for starting using the wiring editor.
         *
         * @param {Wirecloud.Workspace} workspace
         *     workspace to load
         *
         * @returns {Wirecloud.ui.WiringEditor}
         *
         */
        load(workspace) {
            this.workspace = workspace;
            this.errorMessages = [];

            readyView.call(this);
            loadWiringStatus.call(this);

            Wirecloud.UserInterfaceManager.rootKeydownHandler = document_onkeydown.bind(this);
            this.enable();

            // Themes can enable creating connections by clicking an output and then an input
            const config = Wirecloud.currentTheme != null && Wirecloud.currentTheme.config != null ? Wirecloud.currentTheme.config : {};
            this.connectionEngine.clickToConnect = config.wiring_click_to_connect === true;

            return this;
        }

        /**
         * Unload any resource used for the user interface leaving the Wiring
         * Editor ready for loading another wiring configuration.
         *
         * @returns {Wirecloud.ui.WiringEditor}
         *
         */
        unload() {
            this.workspace.wiring.load(this.toJSON()).save().catch((error) => {
                (new Wirecloud.ui.MessageWindowMenu(
                    error,
                    Wirecloud.constants.LOGGING.ERROR_MSG
                )).show();
            });
            readyView.call(this);

            Wirecloud.UserInterfaceManager.rootKeydownHandler = null;
            this.disable();

            return this;
        }

        /**
         * Serializes current wiring configuration
         *
         * @returns {PlainObject}
         *      Object with the wiring status version of the edited wiring
         *      configuration, usable by the wiring engine.
         */
        toJSON() {
            const wiringStatus = Wirecloud.Wiring.normalize();

            this.connectionEngine.forEachConnection((connection) => {
                wiringStatus.connections.push(connection._connection);
            });

            this.behaviourEngine.forEachComponent((component) => {
                if (component.type === 'operator') {
                    wiringStatus.operators[component.id] = component._component;
                }
            });

            wiringStatus.visualdescription = this.behaviourEngine.toJSON();

            return wiringStatus;
        }

    }
    ns.WiringEditor.prototype.view_name = "wiring";

})(Wirecloud.ui, StyledElements, StyledElements.Utils);
