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

    const GROUP_LABELS = {
        workspaces: () => utils.gettext("Workspaces"),
        commands: () => utils.gettext("Commands"),
        navigation: () => utils.gettext("Navigation"),
        resources: () => utils.gettext("Resources")
    };

    let instance_counter = 0;

    const update_highlight = function update_highlight(index, scroll) {
        const items = this.listElement.querySelectorAll('.wc-palette-item');
        if (items.length === 0) {
            this.highlighted = -1;
            this.inputElement.removeAttribute('aria-activedescendant');
            return;
        }

        this.highlighted = Math.max(0, Math.min(items.length - 1, index));
        items.forEach((item, i) => {
            const selected = i === this.highlighted;
            item.classList.toggle('highlighted', selected);
            item.setAttribute('aria-selected', selected ? 'true' : 'false');
        });

        const item = items[this.highlighted];
        this.inputElement.setAttribute('aria-activedescendant', item.id);
        if (scroll && typeof item.scrollIntoView === 'function') {
            item.scrollIntoView({block: 'nearest'});
        }
    };

    const render = function render() {
        const query = this.inputElement.value;
        let commands = this.registry.list(query, {groups: this.options.groups}).filter((command) => command.enabled);

        if (Array.isArray(this.options.groups) && this.options.groups.indexOf('workspaces') !== -1 && this.options.groups.length === 1) {
            // Workspace switcher: offer creating a new workspace
            const create = this.registry.list(query).find((command) => command.id === 'workspace.new');
            if (create != null) {
                commands = commands.concat([Object.assign({}, create, {group: 'workspaces'})]);
            }
        }

        this.commands = commands;
        this.listElement.innerHTML = '';

        if (commands.length === 0) {
            this.listElement.appendChild(Industry.element('div', 'wc-palette-empty', [
                query.trim() === '' ?
                    utils.gettext("No commands available.") :
                    utils.interpolate(utils.gettext("No results for “%(query)s”."), {query: query.trim()}, true)
            ]));
            update_highlight.call(this, -1);
            return;
        }

        let group = null;
        let groupElement = null;
        commands.forEach((command, index) => {
            if (command.group !== group) {
                group = command.group;
                const labelId = this.id + '-group-' + group;
                groupElement = Industry.element('div', 'wc-palette-group');
                groupElement.setAttribute('role', 'group');
                groupElement.setAttribute('aria-labelledby', labelId);
                const label = Industry.element('div', 'wc-palette-group-label', [
                    group in GROUP_LABELS ? GROUP_LABELS[group]() : group
                ]);
                label.id = labelId;
                groupElement.appendChild(label);
                this.listElement.appendChild(groupElement);
            }

            const item = Industry.element('div', 'wc-palette-item' + (command.danger ? ' danger' : ''));
            item.id = this.id + '-item-' + index;
            item.setAttribute('role', 'option');
            item.dataset.index = index;

            const icon = Industry.iconFromClass(command.icon) || Industry.icon('command');
            icon.classList.add('wc-palette-item-icon');
            item.appendChild(icon);

            const text = Industry.element('span', 'wc-palette-item-text', [
                Industry.element('span', 'wc-palette-item-label', [command.label])
            ]);
            if (command.description) {
                text.appendChild(Industry.element('span', 'wc-palette-item-description', [command.description]));
            }
            item.appendChild(text);

            if (command.hint) {
                item.appendChild(Industry.element('span', 'wc-palette-item-hint', [command.hint]));
            }
            if (command.shortcut) {
                item.appendChild(Industry.element('kbd', 'wc-palette-item-shortcut', [String(command.shortcut).toUpperCase()]));
            }

            item.addEventListener('mousemove', () => {
                if (this.highlighted !== index) {
                    update_highlight.call(this, index, false);
                }
            });
            item.addEventListener('click', (event) => {
                event.preventDefault();
                run.call(this, index);
            });

            groupElement.appendChild(item);
        });

        update_highlight.call(this, 0, true);
    };

    const run = function run(index) {
        const command = this.commands[index];
        if (command == null) {
            return;
        }

        this.hide();
        try {
            const result = this.registry.run(command);
            if (result != null && typeof result.catch === 'function') {
                result.catch((error) => {
                    Industry.toast(typeof error === 'string' ? error : utils.gettext("The command could not be completed"));
                });
            }
        } catch (error) {
            Industry.toast(utils.gettext("The command could not be completed"));
            Wirecloud.GlobalLogManager.log(error);
        }
    };

    const on_keydown = function on_keydown(event) {
        const key = utils.normalizeKey(event);

        switch (key) {
        case 'ArrowDown':
            event.preventDefault();
            update_highlight.call(this, this.highlighted + 1, true);
            break;
        case 'ArrowUp':
            event.preventDefault();
            update_highlight.call(this, this.highlighted - 1, true);
            break;
        case 'Home':
            if (event.ctrlKey || event.metaKey) {
                event.preventDefault();
                update_highlight.call(this, 0, true);
            }
            break;
        case 'End':
            if (event.ctrlKey || event.metaKey) {
                event.preventDefault();
                update_highlight.call(this, this.commands.length - 1, true);
            }
            break;
        case 'Enter':
            event.preventDefault();
            run.call(this, this.highlighted);
            break;
        case 'Escape':
            event.preventDefault();
            event.stopPropagation();
            this.hide();
            break;
        case 'Tab':
            // Keep the focus inside the palette
            event.preventDefault();
            break;
        default:
            // ⌘K must reach the platform shortcut service (it toggles the
            // palette), other keys are only for the input
            if (!((event.metaKey || event.ctrlKey) && key.toLowerCase() === 'k')) {
                event.stopPropagation();
            }
        }
    };

    /**
     * Command palette (⌘K) listing the commands of `Wirecloud.commands`.
     * Registered as `CommandPalette` in `Wirecloud.ui.registry`.
     */
    Industry.CommandPalette = class CommandPalette {

        constructor(registry) {
            this.registry = registry || Wirecloud.commands;
            this.id = 'wc-palette-' + (++instance_counter);
            this.commands = [];
            this.highlighted = -1;
            this.options = {};

            this.backdrop = Industry.element('div', 'wc-palette-backdrop');
            this.backdrop.addEventListener('mousedown', (event) => {
                event.preventDefault();
                this.hide();
            });

            this.wrapperElement = Industry.blueprint(Industry.element('div', 'wc-palette'));
            this.wrapperElement.setAttribute('role', 'dialog');
            this.wrapperElement.setAttribute('aria-modal', 'true');
            this.wrapperElement.setAttribute('aria-label', utils.gettext("Command palette"));

            this.inputElement = document.createElement('input');
            this.inputElement.type = 'text';
            this.inputElement.className = 'wc-palette-input';
            this.inputElement.setAttribute('role', 'combobox');
            this.inputElement.setAttribute('aria-expanded', 'true');
            this.inputElement.setAttribute('aria-controls', this.id + '-list');
            this.inputElement.setAttribute('aria-autocomplete', 'list');
            this.inputElement.setAttribute('autocomplete', 'off');
            this.inputElement.setAttribute('spellcheck', 'false');
            this.inputElement.addEventListener('input', render.bind(this));
            this.inputElement.addEventListener('keydown', on_keydown.bind(this));

            const searchIcon = Industry.icon('search');
            searchIcon.classList.add('wc-palette-search-icon');
            this.wrapperElement.appendChild(Industry.element('div', 'wc-palette-input-row', [
                searchIcon,
                this.inputElement,
                Industry.element('kbd', 'wc-palette-esc', ['esc'])
            ]));

            this.listElement = Industry.element('div', 'wc-palette-list');
            this.listElement.id = this.id + '-list';
            this.listElement.setAttribute('role', 'listbox');
            this.wrapperElement.appendChild(this.listElement);

            this.wrapperElement.appendChild(Industry.element('div', 'wc-palette-footer', [
                Industry.element('span', null, [utils.gettext("↑↓ navigate")]),
                Industry.element('span', null, [utils.gettext("↵ run")]),
                Industry.element('span', null, [utils.gettext("esc close")])
            ]));
        }

        isVisible() {
            return this.wrapperElement.isConnected;
        }

        /**
         * @param {Object} [options]
         * @param {Array.<String>} [options.groups] only list these command groups
         * @param {String} [options.placeholder]
         * @param {String} [options.query] initial query
         */
        show(options) {
            this.options = Object.assign({}, options);
            const workspacesOnly = Array.isArray(this.options.groups) && this.options.groups.length === 1 && this.options.groups[0] === 'workspaces';
            this.inputElement.placeholder = this.options.placeholder || (workspacesOnly ? utils.gettext("Switch workspace…") : utils.gettext("Type a command or search…"));
            this.inputElement.value = this.options.query || '';

            if (!this.isVisible()) {
                this.previousFocus = document.activeElement;
                const base = utils.getFullscreenElement() || document.body;
                base.appendChild(this.backdrop);
                base.appendChild(this.wrapperElement);
                document.documentElement.classList.add('wc-palette-open');
            }

            render.call(this);
            this.inputElement.focus();
            return this;
        }

        hide() {
            if (!this.isVisible()) {
                return this;
            }

            this.backdrop.remove();
            this.wrapperElement.remove();
            document.documentElement.classList.remove('wc-palette-open');
            if (this.previousFocus != null && typeof this.previousFocus.focus === 'function' && this.previousFocus.isConnected) {
                this.previousFocus.focus();
            }
            this.previousFocus = null;
            return this;
        }

    };

    Wirecloud.ui.registry.register('CommandPalette', Industry.CommandPalette);

})(Wirecloud.ui.Industry, Wirecloud.Utils);
