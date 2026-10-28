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

    // Feeds Wirecloud.commands from the existing menu builders, so menus and
    // the command palette share the same source, and registers the default
    // keyboard shortcuts (only active when the theme enables them).

    const commands = Wirecloud.commands;
    const MAX_RESOURCES = 6;

    const is_anonymous = function is_anonymous() {
        return Wirecloud.contextManager == null || Wirecloud.contextManager.get('isanonymous') !== false;
    };

    const get_views = function get_views() {
        const uim = Wirecloud.UserInterfaceManager;
        return uim != null && uim.views != null ? uim.views : {};
    };

    const get_current_view = function get_current_view() {
        const uim = Wirecloud.UserInterfaceManager;
        return uim != null && typeof uim.getCurrentView === 'function' ? uim.getCurrentView() : null;
    };

    const get_workspace_view = function get_workspace_view() {
        const view = get_views().workspace;
        return view != null && view.model != null ? view : null;
    };

    const is_editable = function is_editable() {
        const view = get_workspace_view();
        return view != null && !is_anonymous() && view.model.isAllowed('edit');
    };

    // Workspace menu ("New workspace", "Rename", "Share", ...)
    commands.registerProvider('workspace', () => {
        const view = get_workspace_view();
        if (view == null || is_anonymous()) {
            return [];
        }

        return commands.fromMenuItems(new ns.WorkspaceViewMenuItems(view), {
            group: 'commands',
            idPrefix: 'workspace.'
        });
    });

    // Tab menu ("Rename", "Settings", "Remove"), available while editing
    commands.registerProvider('tab', () => {
        const view = get_workspace_view();
        if (view == null || !view.editing || view.activeTab == null || !view.model.isAllowed('edit')) {
            return [];
        }

        return commands.fromMenuItems(new ns.WorkspaceTabViewMenuItems(view.activeTab), {
            group: 'commands',
            idPrefix: 'tab.'
        });
    });

    // Menu of the selected widget
    commands.registerProvider('widget', () => {
        const view = get_workspace_view();
        const widget = view != null ? view.selectedWidget : null;
        if (widget == null || !view.editing) {
            return [];
        }

        return commands.fromMenuItems(new ns.WidgetViewMenuItems(widget), {
            group: 'commands',
            idPrefix: 'widget.'
        }).map((command) => {
            command.description = widget.title;
            return command;
        });
    });

    // Marketplace menu, while the marketplace is the current view
    commands.registerProvider('marketplace', () => {
        const view = get_current_view();
        if (view == null || view !== get_views().marketplace || typeof ns.MarketplaceViewMenuItems !== 'function') {
            return [];
        }

        return commands.fromMenuItems(new ns.MarketplaceViewMenuItems(view), {
            group: 'commands',
            idPrefix: 'marketplace.'
        });
    });

    // Workspace list (same source as Wirecloud.ui.WorkspaceListItems)
    commands.registerProvider('workspaces', () => {
        const active = Wirecloud.activeWorkspace;
        const result = [];

        Object.keys(Wirecloud.workspacesByUserAndName || {}).forEach((owner) => {
            const workspaces = Wirecloud.workspacesByUserAndName[owner];
            Object.keys(workspaces).forEach((name) => {
                const workspace = workspaces[name];
                const current = active != null && active.id === workspace.id;

                result.push({
                    id: 'workspaces.' + workspace.id,
                    group: 'workspaces',
                    label: owner + ' / ' + (workspace.title || workspace.name),
                    description: workspace.description || '',
                    keywords: workspace.name,
                    icon: workspace.public ? 'fas fa-globe' : 'fas fa-lock',
                    hint: current ? utils.gettext('Current') : '',
                    current: current,
                    workspace: workspace,
                    run: () => {
                        if (current) {
                            Wirecloud.UserInterfaceManager.changeCurrentView('workspace');
                            return;
                        }
                        Wirecloud.UserInterfaceManager.monitorTask(Wirecloud.changeActiveWorkspace(workspace));
                    }
                });
            });
        });

        // Current workspace first, then the ones of the user
        const username = Wirecloud.contextManager != null ? Wirecloud.contextManager.get('username') : null;
        result.sort((a, b) => {
            if (a.current !== b.current) {
                return a.current ? -1 : 1;
            }
            const aOwn = a.workspace.owner === username, bOwn = b.workspace.owner === username;
            if (aOwn !== bOwn) {
                return aOwn ? -1 : 1;
            }
            return a.label.localeCompare(b.label);
        });

        return result;
    });

    // Navigation
    commands.registerProvider('navigation', () => {
        const result = [];
        const views = get_views();
        const current = get_current_view();

        const modeSource = current != null && typeof current.getModes === 'function' ? current : get_workspace_view();
        if (modeSource != null && typeof modeSource.getModes === 'function') {
            modeSource.getModes().forEach((mode) => {
                if (mode.active && current === modeSource) {
                    return;
                }
                result.push({
                    id: 'mode.' + mode.id,
                    group: 'navigation',
                    label: utils.interpolate(utils.gettext('Switch to %(mode)s mode'), {mode: mode.label}),
                    icon: mode.icon,
                    shortcut: mode.shortcut,
                    enabled: mode.enabled,
                    run: () => {
                        if (current !== modeSource) {
                            Wirecloud.UserInterfaceManager.changeCurrentView('workspace');
                        }
                        mode.activate();
                    }
                });
            });
        }

        if (!is_anonymous() && views.myresources != null && current !== views.myresources) {
            result.push({
                id: 'navigation.myresources',
                group: 'navigation',
                label: utils.gettext('Go to My resources'),
                icon: 'fas fa-archive',
                run: () => Wirecloud.UserInterfaceManager.changeCurrentView('myresources')
            });
        }

        if (!is_anonymous() && views.marketplace != null && current !== views.marketplace) {
            result.push({
                id: 'navigation.marketplace',
                group: 'navigation',
                label: utils.gettext('Go to Marketplace'),
                icon: 'fas fa-shopping-cart',
                run: () => Wirecloud.UserInterfaceManager.changeCurrentView('marketplace')
            });
        }

        const colorScheme = ns.ColorScheme;
        if (colorScheme != null && colorScheme.supported.indexOf('dark') !== -1 && colorScheme.supported.indexOf('light') !== -1) {
            const dark = colorScheme.resolve() === 'dark';
            result.push({
                id: 'navigation.colorscheme',
                group: 'navigation',
                label: dark ? utils.gettext('Switch to light color scheme') : utils.gettext('Switch to dark color scheme'),
                icon: dark ? 'fas fa-sun' : 'fas fa-moon',
                run: () => colorScheme.toggle()
            });
        }

        return result;
    });

    // Installed components: add widgets to the current tab / operators to the wiring
    commands.registerProvider('resources', (query) => {
        const catalogue = Wirecloud.LocalCatalogue;
        if (query === '' || !is_editable() || catalogue == null || catalogue.resourceVersions == null) {
            return [];
        }

        const result = [];
        Object.keys(catalogue.resourceVersions).forEach((groupId) => {
            const versions = catalogue.resourceVersions[groupId];
            if (versions.length === 0) {
                return;
            }

            // Use the latest version
            const resource = versions.reduce((latest, candidate) => {
                if (candidate.version == null || typeof candidate.version.compareTo !== 'function') {
                    return latest;
                }
                return candidate.version.compareTo(latest.version) > 0 ? candidate : latest;
            });

            const haystack = commands.normalize([resource.title, resource.name, resource.vendor, resource.description].join(' '));
            if (query.split(/\s+/).some((word) => haystack.indexOf(word) === -1)) {
                return;
            }

            if (resource.type === 'widget') {
                result.push({
                    id: 'resources.' + resource.uri,
                    group: 'resources',
                    label: resource.title,
                    description: resource.vendor + ' · ' + utils.gettext('widget'),
                    keywords: [resource.name, resource.vendor, resource.description].join(' '),
                    icon: 'fas fa-puzzle-piece',
                    hint: utils.gettext('Add to tab'),
                    requiresQuery: true,
                    resource: resource,
                    run: () => {
                        const view = get_workspace_view();
                        Wirecloud.UserInterfaceManager.changeCurrentView('workspace');
                        view.setEditing(true);
                        return view.activeTab.createWidget(resource);
                    }
                });
            } else if (resource.type === 'operator') {
                result.push({
                    id: 'resources.' + resource.uri,
                    group: 'resources',
                    label: resource.title,
                    description: resource.vendor + ' · ' + utils.gettext('operator'),
                    keywords: [resource.name, resource.vendor, resource.description].join(' '),
                    icon: 'fas fa-cogs',
                    hint: utils.gettext('Add to wiring'),
                    requiresQuery: true,
                    resource: resource,
                    run: () => {
                        return Wirecloud.activeWorkspace.wiring.createOperator(resource).then(() => {
                            Wirecloud.UserInterfaceManager.changeCurrentView('wiring');
                        });
                    }
                });
            }
        });

        return result.slice(0, MAX_RESOURCES);
    });

    // Default keyboard shortcuts
    const shortcuts = ns.shortcuts;

    shortcuts.register({
        id: 'palette',
        keys: 'mod+k',
        label: utils.gettext('Commands'),
        allowInInputs: true,
        run: () => {
            if (commands.isPaletteOpen()) {
                commands.closePalette();
                return true;
            }
            return commands.openPalette();
        }
    });

    const switch_mode = function switch_mode(id) {
        const view = get_current_view();
        if (view == null || typeof view.getModes !== 'function') {
            return false;
        }

        const mode = view.getModes().find((entry) => entry.id === id);
        if (mode == null || !mode.enabled) {
            return false;
        }
        if (!mode.active) {
            mode.activate();
        }
        return true;
    };

    [['view', 'v'], ['edit', 'e'], ['wiring', 'w']].forEach(([id, key]) => {
        shortcuts.register({
            id: 'mode.' + id,
            keys: key,
            label: utils.gettext('Change mode'),
            run: () => switch_mode(id)
        });
    });

    shortcuts.register({
        id: 'delete-selection',
        keys: ['Delete', 'Backspace'],
        label: utils.gettext('Remove selection'),
        run: () => {
            const view = get_current_view();
            if (view == null || typeof view.deleteSelection !== 'function') {
                return false;
            }
            return view.deleteSelection();
        }
    });

    shortcuts.register({
        id: 'cancel',
        keys: 'Escape',
        label: utils.gettext('Cancel'),
        allowInInputs: true,
        run: () => {
            if (Wirecloud.UserInterfaceManager.hasPopups()) {
                // Let the platform close tooltips, popups and dialogs
                return false;
            }

            const view = get_current_view();
            if (view == null || typeof view.cancel !== 'function') {
                return false;
            }
            return view.cancel();
        }
    });

})(Wirecloud.ui, Wirecloud.Utils);
