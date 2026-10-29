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


(function (se, utils) {

    "use strict";

    const GROUP_ORDER = ["workspaces", "commands", "navigation", "resources"];

    const normalize = function normalize(text) {
        return String(text == null ? "" : text)
            .toLowerCase()
            .normalize("NFD")
            .replace(/[̀-ͯ]/g, "");
    };

    const call_condition = function call_condition(command) {
        if (typeof command.when !== "function") {
            return true;
        }

        try {
            return command.when() !== false;
        } catch (e) {
            return false;
        }
    };

    const is_enabled = function is_enabled(command) {
        if (typeof command.enabled === "function") {
            try {
                return command.enabled() !== false;
            } catch (e) {
                return false;
            }
        }
        return command.enabled !== false;
    };

    /**
     * Returns a ranking for a command given a normalized query, or -1 if the
     * command does not match.
     */
    const score = function score(command, query) {
        if (query === "") {
            return 0;
        }

        const label = normalize(command.label);
        const haystack = [label, normalize(command.description), normalize(command.keywords)].join(" ");
        const words = query.split(/\s+/).filter((word) => word !== "");

        if (!words.every((word) => haystack.indexOf(word) !== -1)) {
            return -1;
        }

        if (label.startsWith(query)) {
            return 3;
        } else if (label.indexOf(query) !== -1) {
            return 2;
        }
        return 1;
    };

    const normalize_command = function normalize_command(command, provider) {
        if (command == null || typeof command.run !== "function") {
            throw new TypeError("commands must provide a run function");
        }

        return Object.assign({
            id: null,
            group: "commands",
            icon: null,
            description: "",
            keywords: "",
            hint: "",
            shortcut: null,
            danger: false,
            enabled: true
        }, command, {
            provider: provider != null ? provider : null
        });
    };

    /**
     * Builds commands from the items returned by a
     * {StyledElements.DynamicMenuItems} builder, so the menus and the command
     * palette share the same source (labels, icons, enablement and handlers).
     *
     * @param {StyledElements.DynamicMenuItems} builder
     * @param {Object} [options]
     * @param {String} [options.group]
     * @param {String} [options.idPrefix]
     * @returns {Array.<Object>}
     */
    const from_menu_items = function from_menu_items(builder, options) {
        options = utils.merge({
            group: "commands",
            idPrefix: "",
            context: null
        }, options);

        const commands = [];
        builder.build(options.context).forEach((item, index) => {
            if (!(item instanceof se.MenuItem) || typeof item.run !== "function") {
                // Submenus and separators are only available from menus
                return;
            }

            const id = options.idPrefix + (item.commandId != null ? item.commandId : normalize(item.title).replace(/[^a-z0-9]+/g, "-"));
            commands.push({
                id: id,
                group: options.group,
                label: item.commandLabel != null ? item.commandLabel : item.title,
                description: item.commandDescription != null ? item.commandDescription : "",
                icon: item.iconClass,
                danger: !!item.danger,
                enabled: item.enabled,
                order: index,
                run: function () {
                    return item.run.call(item, options.context, item.context);
                }
            });
        });

        return commands;
    };

    /**
     * Registry of the commands available in the platform. Commands can be
     * registered statically (`register`) or computed when listing them through
     * providers (`registerProvider`), which is how the menu builders feed it.
     *
     * Each command is an object with the following fields:
     *
     * - `id` (`String`)
     * - `label` (`String`)
     * - `run` (`Function`)
     * - `group` (`String`): `workspaces`, `commands`, `navigation`, `resources`...
     * - `icon` (`String`): an icon class (e.g. `fas fa-cog`)
     * - `description`, `keywords`, `hint` (`String`)
     * - `shortcut` (`String`): e.g. `mod+k`
     * - `danger` (`Boolean`)
     * - `enabled` (`Boolean|Function`): disabled commands are listed but cannot run
     * - `when` (`Function`): commands are listed only when it returns `true`
     * - `requiresQuery` (`Boolean`): only list the command for non-empty queries
     *
     * @namespace Wirecloud.commands
     */
    const CommandRegistry = class CommandRegistry extends se.ObjectWithEvents {

        constructor() {
            super(["change", "paletterequest"]);
            this._commands = new Map();
            this._providers = new Map();
            this._palette = null;
        }

        /**
         * @param {Object} command
         * @returns {Wirecloud.commands}
         */
        register(command) {
            const normalized = normalize_command(command);
            if (typeof normalized.id !== "string" || normalized.id === "") {
                throw new TypeError("commands must provide an id");
            }
            this._commands.set(normalized.id, normalized);
            this.dispatchEvent("change");
            return this;
        }

        /**
         * @param {String} id
         * @returns {Wirecloud.commands}
         */
        unregister(id) {
            if (this._commands.delete(id)) {
                this.dispatchEvent("change");
            }
            return this;
        }

        /**
         * Registers a function that computes commands every time the command
         * list is requested.
         *
         * @param {String} id
         * @param {Function} provider `function (query) -> Array.<Object>`
         * @returns {Wirecloud.commands}
         */
        registerProvider(id, provider) {
            if (typeof provider !== "function") {
                throw new TypeError("provider must be a function");
            }
            this._providers.set(id, provider);
            this.dispatchEvent("change");
            return this;
        }

        /**
         * @param {String} id
         * @returns {Wirecloud.commands}
         */
        unregisterProvider(id) {
            if (this._providers.delete(id)) {
                this.dispatchEvent("change");
            }
            return this;
        }

        /**
         * Returns the commands available in the current context matching the
         * given query, grouped (`workspaces`, `commands`, `navigation`,
         * `resources`, then any other group) and ranked by relevance.
         *
         * @param {String} [query]
         * @param {Object} [options]
         * @param {Array.<String>} [options.groups] only return these groups
         * @returns {Array.<Object>}
         */
        list(query, options) {
            options = utils.merge({
                groups: null
            }, options);

            const normalizedQuery = normalize(query).trim();
            const candidates = Array.from(this._commands.values());

            this._providers.forEach((provider, providerId) => {
                let provided;
                try {
                    provided = provider(normalizedQuery);
                } catch (e) {
                    provided = [];
                }

                if (Array.isArray(provided)) {
                    provided.forEach((command, index) => {
                        const normalized = normalize_command(command, providerId);
                        if (normalized.id == null) {
                            normalized.id = providerId + ":" + index;
                        }
                        candidates.push(normalized);
                    });
                }
            });

            const results = [];
            candidates.forEach((command, index) => {
                if (options.groups != null && options.groups.indexOf(command.group) === -1) {
                    return;
                }
                if (command.requiresQuery && normalizedQuery === "") {
                    return;
                }
                if (!call_condition(command)) {
                    return;
                }

                const commandScore = score(command, normalizedQuery);
                if (commandScore === -1) {
                    return;
                }

                results.push({command: command, score: commandScore, index: index});
            });

            const groupIndex = (group) => {
                const index = GROUP_ORDER.indexOf(group);
                return index === -1 ? GROUP_ORDER.length : index;
            };

            results.sort((a, b) => {
                const groupDiff = groupIndex(a.command.group) - groupIndex(b.command.group);
                if (groupDiff !== 0) {
                    return groupDiff;
                }
                if (b.score !== a.score) {
                    return b.score - a.score;
                }
                return a.index - b.index;
            });

            return results.map((entry) => Object.assign({}, entry.command, {
                enabled: is_enabled(entry.command)
            }));
        }

        /**
         * @param {String} id
         * @returns {Object|null}
         */
        get(id) {
            return this.list("").find((command) => command.id === id) || null;
        }

        /**
         * Runs a command, if it is available and enabled.
         *
         * @param {String|Object} command command or command id
         * @returns {*} the value returned by the command or `undefined` if it
         * could not be run
         */
        run(command) {
            if (typeof command === "string") {
                command = this.get(command);
            }

            if (command == null || !call_condition(command) || !is_enabled(command)) {
                return undefined;
            }

            return command.run();
        }

        /**
         * Opens the command palette provided by the current theme (registered
         * as `CommandPalette` in {Wirecloud.ui.registry}).
         *
         * @param {Object} [options] e.g. `{groups: ['workspaces']}`
         * @returns {Boolean} `true` if a command palette is available
         */
        openPalette(options) {
            const registry = Wirecloud.ui.registry;
            const Palette = registry != null ? registry.get("CommandPalette") : Wirecloud.ui.CommandPalette;

            if (typeof Palette !== "function") {
                return false;
            }

            if (this._palette == null || !(this._palette instanceof Palette)) {
                this._palette = new Palette(this);
            }

            this.dispatchEvent("paletterequest", options);
            this._palette.show(options);
            return true;
        }

        /**
         * @returns {Boolean} `true` if the command palette is currently open
         */
        isPaletteOpen() {
            return this._palette != null && typeof this._palette.isVisible === "function" && this._palette.isVisible();
        }

        /**
         * Closes the command palette, if open.
         *
         * @returns {Wirecloud.commands}
         */
        closePalette() {
            if (this.isPaletteOpen()) {
                this._palette.hide();
            }
            return this;
        }

    };

    CommandRegistry.prototype.fromMenuItems = from_menu_items;
    CommandRegistry.prototype.normalize = normalize;

    Wirecloud.CommandRegistry = CommandRegistry;
    Wirecloud.commands = new CommandRegistry();

})(StyledElements, Wirecloud.Utils);
