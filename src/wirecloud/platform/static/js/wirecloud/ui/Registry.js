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


(function (ns) {

    "use strict";

    const overrides = new Map();

    const lookup = function lookup(name) {
        return name.split('.').reduce((value, key) => {
            return value != null ? value[key] : undefined;
        }, ns);
    };

    /**
     * Registry of replaceable user interface classes. The platform builds its
     * main UI pieces (`WirecloudHeader`, `WorkspaceToolbar`, `WidgetView`,
     * `ResourcePainter`, `MyResourcesSearchView`, `WiringEditor.Component`,
     * ...) through this registry so themes can provide their own
     * implementations from their scripts (which run after the platform ones).
     *
     * When nothing has been registered for a name, the class available at the
     * same path inside `Wirecloud.ui` is used, so the platform behaves exactly
     * as before unless a theme registers a replacement.
     *
     * @namespace Wirecloud.ui.registry
     */
    ns.registry = {

        /**
         * Registers a replacement for a UI class.
         *
         * @param {String} name e.g. `"WirecloudHeader"` or `"WiringEditor.Component"`
         * @param {Function} constructor
         * @returns {Wirecloud.ui.registry}
         */
        register: function register(name, constructor) {
            if (typeof name !== "string" || name === "") {
                throw new TypeError("name must be a non-empty string");
            }
            if (typeof constructor !== "function") {
                throw new TypeError("constructor must be a function");
            }

            overrides.set(name, constructor);
            return this;
        },

        /**
         * Removes the replacement registered for a UI class (if any).
         *
         * @param {String} name
         * @returns {Wirecloud.ui.registry}
         */
        unregister: function unregister(name) {
            overrides.delete(name);
            return this;
        },

        /**
         * @param {String} name
         * @returns {Boolean} `true` if a replacement has been registered
         */
        has: function has(name) {
            return overrides.has(name);
        },

        /**
         * Returns the class to use for the given name: the registered
         * replacement, the platform class at `Wirecloud.ui.<name>` or, if
         * none of them exists, `defaultValue`.
         *
         * @param {String} name
         * @param {Function} [defaultValue]
         * @returns {Function}
         */
        get: function get(name, defaultValue) {
            if (overrides.has(name)) {
                return overrides.get(name);
            }

            const value = lookup(name);
            return value != null ? value : defaultValue;
        },

        /**
         * Builds an instance of the class registered for the given name.
         *
         * @param {String} name
         * @param {...*} args constructor arguments
         * @returns {Object}
         */
        create: function create(name, ...args) {
            const Constructor = this.get(name);
            if (typeof Constructor !== "function") {
                throw new TypeError("No UI class available for " + name);
            }

            return new Constructor(...args);
        }

    };

})(Wirecloud.ui);
