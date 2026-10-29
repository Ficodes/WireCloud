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


(function (ns, se) {

    "use strict";

    const PREFERENCE = "color-scheme";
    const STORAGE_KEY = "wirecloud.color-scheme";
    const PREFERENCE_STORAGE_KEY = "wirecloud.color-scheme-preference";
    const ATTRIBUTE = "data-wc-color-scheme";
    const VALID_PREFERENCES = ["system", "light", "dark"];

    const get_media_query = function get_media_query() {
        if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
            return null;
        }
        return window.matchMedia("(prefers-color-scheme: dark)");
    };

    const get_storage = function get_storage() {
        try {
            return window.localStorage;
        } catch (e) {
            return null;
        }
    };

    const read_storage = function read_storage(key) {
        const storage = get_storage();
        try {
            return storage != null ? storage.getItem(key) : null;
        } catch (e) {
            return null;
        }
    };

    const write_storage = function write_storage(key, value) {
        const storage = get_storage();
        try {
            if (storage != null) {
                storage.setItem(key, value);
            }
        } catch (e) {
            // Ignore storage errors (e.g. private mode)
        }
    };

    const is_anonymous = function is_anonymous() {
        return Wirecloud.contextManager == null || Wirecloud.contextManager.get('isanonymous') !== false;
    };

    /**
     * Resolves the `color-scheme` platform preference into the color scheme
     * used by the user interface, exposing it through the
     * `data-wc-color-scheme` attribute of the root element (and the root
     * element of the widget documents).
     *
     * The schemes supported by the active theme come from the
     * `color_schemes` entry of its config (`["light"]` by default).
     *
     * @namespace Wirecloud.ui.ColorScheme
     */
    const ColorScheme = class ColorScheme extends se.ObjectWithEvents {

        constructor() {
            super(["change"]);
            this.current = null;
            this._override = null;
            this._initialized = false;
            this._on_system_change = () => {
                if (this.preference === "system") {
                    this.apply();
                }
            };
            this._on_preferences_commit = (preferences, modifiedValues) => {
                if (modifiedValues != null && PREFERENCE in modifiedValues) {
                    this._override = null;
                    this.apply();
                }
            };
        }

        /**
         * Color schemes supported by the active theme
         *
         * @type {Array.<String>}
         */
        get supported() {
            const theme = Wirecloud.currentTheme;
            const schemes = theme != null && theme.config != null ? theme.config.color_schemes : null;
            return Array.isArray(schemes) && schemes.length > 0 ? schemes : ["light"];
        }

        /**
         * Current value of the `color-scheme` preference
         * (`system`, `light` or `dark`).
         *
         * @type {String}
         */
        get preference() {
            let value = this._override;
            if (value == null && is_anonymous()) {
                // Anonymous users cannot store platform preferences
                value = read_storage(PREFERENCE_STORAGE_KEY);
            } else if (value == null && Wirecloud.preferences != null && typeof Wirecloud.preferences.get === "function") {
                try {
                    value = Wirecloud.preferences.get(PREFERENCE);
                } catch (e) {
                    value = null;
                }
            }
            return VALID_PREFERENCES.indexOf(value) !== -1 ? value : "system";
        }

        /**
         * @returns {String} color scheme to use (`light` or `dark`)
         */
        resolve(preference) {
            if (preference == null) {
                preference = this.preference;
            }

            let scheme = preference;
            if (preference === "system") {
                const query = get_media_query();
                scheme = query != null && query.matches ? "dark" : "light";
            }

            const supported = this.supported;
            return supported.indexOf(scheme) !== -1 ? scheme : supported[0];
        }

        init() {
            if (!this._initialized) {
                this._initialized = true;

                const query = get_media_query();
                if (query != null) {
                    if (typeof query.addEventListener === "function") {
                        query.addEventListener("change", this._on_system_change);
                    } else if (typeof query.addListener === "function") {
                        query.addListener(this._on_system_change);
                    }
                }

                if (Wirecloud.preferences != null && typeof Wirecloud.preferences.addEventListener === "function") {
                    Wirecloud.preferences.addEventListener("post-commit", this._on_preferences_commit);
                }
            }

            return this.apply();
        }

        /**
         * Applies the resolved color scheme to the platform and to the loaded
         * widgets.
         *
         * @returns {Wirecloud.ui.ColorScheme}
         */
        apply(scheme) {
            if (scheme == null) {
                scheme = this.resolve();
            }

            const changed = scheme !== this.current;
            this.current = scheme;

            if (typeof document !== "undefined" && document.documentElement != null) {
                document.documentElement.setAttribute(ATTRIBUTE, scheme);
                if (typeof document.querySelectorAll === "function") {
                    document.querySelectorAll(".wc-widget-content").forEach((element) => {
                        this.applyTo(element, scheme);
                    });
                }
            }

            // Remember the scheme so pages can apply it before loading the
            // platform code, avoiding a flash of the wrong scheme ("system"
            // lets the stylesheets follow the system setting)
            write_storage(STORAGE_KEY, this.preference === "system" ? "system" : scheme);

            if (changed) {
                this.dispatchEvent("change", scheme);
            }

            return this;
        }

        /**
         * Propagates the color scheme to a widget element: the root element of
         * its document (iframe based widgets) or the element itself (shadow DOM
         * based widgets, styled using `:host([data-wc-color-scheme])`).
         *
         * @param {Element} element
         * @param {String} [scheme]
         * @returns {Wirecloud.ui.ColorScheme}
         */
        applyTo(element, scheme) {
            if (element == null) {
                return this;
            }

            if (scheme == null) {
                scheme = this.current != null ? this.current : this.resolve();
            }

            if (element.tagName != null && element.tagName.toUpperCase() === "IFRAME") {
                try {
                    const root = element.contentDocument != null ? element.contentDocument.documentElement : null;
                    if (root != null) {
                        root.setAttribute(ATTRIBUTE, scheme);
                    }
                } catch (e) {
                    // Cross-origin documents cannot be accessed
                }
            } else if (typeof element.setAttribute === "function") {
                element.setAttribute(ATTRIBUTE, scheme);
            }

            return this;
        }

        /**
         * Changes the `color-scheme` preference
         *
         * @param {String} value `system`, `light` or `dark`
         * @returns {Promise}
         */
        setPreference(value) {
            if (VALID_PREFERENCES.indexOf(value) === -1) {
                return Promise.reject(new TypeError("invalid color scheme: " + value));
            }

            // Apply immediately, persistence is done in background
            this._override = value;
            this.apply();

            if (is_anonymous()) {
                write_storage(PREFERENCE_STORAGE_KEY, value);
            } else if (Wirecloud.preferences != null && typeof Wirecloud.preferences.set === "function") {
                return Promise.resolve(Wirecloud.preferences.set({[PREFERENCE]: {value: value}})).catch((error) => {
                    if (Wirecloud.GlobalLogManager != null) {
                        Wirecloud.GlobalLogManager.log(error);
                    }
                });
            }

            return Promise.resolve();
        }

        /**
         * Switches between the light and dark schemes (when the theme supports
         * both of them).
         *
         * @returns {Promise}
         */
        toggle() {
            const next = this.resolve() === "dark" ? "light" : "dark";
            if (this.supported.indexOf(next) === -1) {
                return Promise.resolve();
            }
            return this.setPreference(next);
        }

    };

    ColorScheme.STORAGE_KEY = STORAGE_KEY;
    ColorScheme.PREFERENCE_STORAGE_KEY = PREFERENCE_STORAGE_KEY;
    ns.ColorSchemeManager = ColorScheme;
    ns.ColorScheme = new ColorScheme();

})(Wirecloud.ui, StyledElements);
