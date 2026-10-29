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


(function (ns, utils) {

    "use strict";

    const MODIFIERS = ["mod", "ctrl", "meta", "alt", "shift"];

    /**
     * Parses a key combination like `mod+k`, `shift+?` or `Delete`.
     * `mod` stands for Cmd on macOS and Ctrl on the other platforms (both are
     * accepted).
     */
    const parse_combo = function parse_combo(combo) {
        const parts = combo.split("+");
        let key = parts.pop();
        if (key === "" && parts.length > 0) {
            // e.g. "mod++"
            key = "+";
            parts.pop();
        }

        const parsed = {key: key.length === 1 ? key.toLowerCase() : key};
        MODIFIERS.forEach((modifier) => {
            parsed[modifier] = parts.indexOf(modifier) !== -1;
        });
        return parsed;
    };

    const matches = function matches(combo, key, modifiers) {
        const normalizedKey = key.length === 1 ? key.toLowerCase() : key;
        if (combo.key !== normalizedKey) {
            return false;
        }

        if (combo.mod) {
            if (!modifiers.ctrlKey && !modifiers.metaKey) {
                return false;
            }
        } else if ((modifiers.ctrlKey && !combo.ctrl) || (modifiers.metaKey && !combo.meta)) {
            return false;
        }

        if (combo.ctrl && !modifiers.ctrlKey) {
            return false;
        }
        if (combo.meta && !modifiers.metaKey) {
            return false;
        }
        if (combo.alt !== !!modifiers.altKey) {
            return false;
        }
        // Shift is only checked when required, as it is needed for typing
        // some characters (e.g. "?")
        return !combo.shift || !!modifiers.shiftKey;
    };

    const is_typing = function is_typing(target) {
        if (target == null || target.tagName == null) {
            return false;
        }

        const tagName = target.tagName.toUpperCase();
        return tagName === "INPUT" || tagName === "TEXTAREA" || tagName === "SELECT" || target.isContentEditable === true;
    };

    /**
     * Small keyboard shortcut service. Shortcuts are only processed while
     * `enabled` is `true` (themes enable it through the `keyboard_shortcuts`
     * entry of their config), so the platform keeps its previous behaviour
     * by default.
     *
     * Shortcut definition:
     *
     * - `id` (`String`)
     * - `keys` (`String|Array.<String>`): e.g. `"mod+k"`, `["Delete", "Backspace"]`
     * - `run` (`Function`): `function (event, key, modifiers)`. Return `false`
     *   to let other handlers process the event.
     * - `when` (`Function`) optional condition
     * - `allowInInputs` (`Boolean`): also run while typing in a form field
     *   (default: `false`)
     * - `allowInModals` (`Boolean`): also run while a modal dialog is
     *   displayed (default: `false`)
     * - `label`, `group` (`String`) optional metadata for help screens
     *
     * @class Wirecloud.ui.ShortcutManager
     */
    ns.ShortcutManager = class ShortcutManager {

        constructor() {
            this.enabled = false;
            this._shortcuts = new Map();
        }

        register(shortcut) {
            if (shortcut == null || typeof shortcut.id !== "string" || typeof shortcut.run !== "function") {
                throw new TypeError("shortcuts require an id and a run function");
            }

            const keys = Array.isArray(shortcut.keys) ? shortcut.keys : [shortcut.keys];
            if (keys.length === 0 || keys.some((combo) => typeof combo !== "string" || combo === "")) {
                throw new TypeError("shortcuts require at least one key combination");
            }

            this._shortcuts.set(shortcut.id, Object.assign({
                allowInInputs: false,
                allowInModals: false
            }, shortcut, {
                keys: keys,
                combos: keys.map(parse_combo)
            }));

            return this;
        }

        unregister(id) {
            this._shortcuts.delete(id);
            return this;
        }

        get(id) {
            return this._shortcuts.get(id) || null;
        }

        list() {
            return Array.from(this._shortcuts.values());
        }

        /**
         * Processes a keydown event.
         *
         * @param {KeyboardEvent} event
         * @param {Object} [context]
         * @param {Boolean} [context.modal] `true` if a modal dialog is open
         * @returns {Boolean} `true` if the event was consumed by a shortcut
         */
        handle(event, context) {
            if (!this.enabled || event == null || event.defaultPrevented) {
                return false;
            }

            context = Object.assign({modal: false}, context);
            const key = utils.normalizeKey(event);
            const modifiers = {
                altKey: !!event.altKey,
                ctrlKey: !!event.ctrlKey,
                metaKey: !!event.metaKey,
                shiftKey: !!event.shiftKey
            };
            const typing = is_typing(event.target);

            for (const shortcut of this._shortcuts.values()) {
                if (typing && !shortcut.allowInInputs) {
                    continue;
                }
                if (context.modal && !shortcut.allowInModals) {
                    continue;
                }
                if (!shortcut.combos.some((combo) => matches(combo, key, modifiers))) {
                    continue;
                }
                if (typeof shortcut.when === "function" && shortcut.when() === false) {
                    continue;
                }

                if (shortcut.run(event, key, modifiers) !== false) {
                    return true;
                }
            }

            return false;
        }

    };

    ns.ShortcutManager.isTyping = is_typing;
    ns.shortcuts = new ns.ShortcutManager();

})(Wirecloud.ui, StyledElements.Utils);
