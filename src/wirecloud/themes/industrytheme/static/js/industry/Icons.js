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

    // Shared helpers of the Industry theme

    const Industry = Wirecloud.ui.Industry = Wirecloud.ui.Industry || {};

    /**
     * Creates a Lucide icon element (see static/css/base/_icon-map.scss).
     *
     * @param {String} name Lucide icon name (e.g. `settings`)
     * @param {Object} [options]
     * @param {Number} [options.size] size in pixels (default: 1em)
     * @param {String} [options.label] accessible label (icons are hidden from
     *   assistive technologies by default)
     * @returns {HTMLElement}
     */
    Industry.icon = function icon(name, options) {
        options = options || {};

        const element = document.createElement('span');
        element.className = 'lc-icon lc-' + name;
        if (options.size != null) {
            element.style.fontSize = options.size + 'px';
        }
        if (options.label) {
            element.setAttribute('role', 'img');
            element.setAttribute('aria-label', options.label);
        } else {
            element.setAttribute('aria-hidden', 'true');
        }
        return element;
    };

    /**
     * Creates an element with the given class names and children
     *
     * @param {String} tagName
     * @param {String} [className]
     * @param {Array.<Node|String>} [children]
     * @returns {HTMLElement}
     */
    Industry.element = function element(tagName, className, children) {
        const node = document.createElement(tagName);
        if (className) {
            node.className = className;
        }
        (children || []).forEach((child) => {
            if (child == null) {
                return;
            }
            node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
        });
        return node;
    };

    /**
     * Creates a button element
     *
     * @param {Object} options
     * @param {String} [options.className]
     * @param {String} [options.icon] Lucide icon name
     * @param {Number} [options.iconSize]
     * @param {String} [options.label] visible label
     * @param {String} [options.title] tooltip/accessible label
     * @param {Function} [options.onclick]
     * @returns {HTMLButtonElement}
     */
    Industry.button = function button(options) {
        const element = document.createElement('button');
        element.type = 'button';
        element.className = options.className || '';
        if (options.icon) {
            element.appendChild(Industry.icon(options.icon, {size: options.iconSize}));
        }
        if (options.label) {
            element.appendChild(Industry.element('span', 'wc-button-label', [options.label]));
        }
        if (options.title) {
            element.title = options.title;
            if (!options.label) {
                element.setAttribute('aria-label', options.title);
            }
        }
        if (typeof options.onclick === 'function') {
            element.addEventListener('click', options.onclick);
        }
        return element;
    };

    /**
     * Adds the "+" registration marks of the blueprint frames to an element
     *
     * @param {HTMLElement} element
     * @returns {HTMLElement}
     */
    Industry.blueprint = function blueprint(element) {
        element.classList.add('blueprint');
        ['tl', 'tr', 'bl', 'br'].forEach((position) => {
            const corner = document.createElement('i');
            corner.className = 'corner ' + position;
            corner.setAttribute('aria-hidden', 'true');
            element.appendChild(corner);
        });
        return element;
    };

    /**
     * Converts an icon class used by the platform (e.g. `fas fa-cog`) into an
     * icon element.
     *
     * @param {String} iconClass
     * @returns {HTMLElement|null}
     */
    Industry.iconFromClass = function iconFromClass(iconClass) {
        if (!iconClass) {
            return null;
        }
        const element = document.createElement('span');
        element.className = 'se-icon ' + iconClass;
        element.setAttribute('aria-hidden', 'true');
        return element;
    };

    /**
     * Returns `true` if the current user is anonymous
     */
    Industry.isAnonymous = function isAnonymous() {
        return Wirecloud.contextManager == null || Wirecloud.contextManager.get('isanonymous') !== false;
    };

    /**
     * Shows the keyboard modifier used by shortcuts in this platform
     */
    Industry.modKey = function modKey() {
        const platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || '';
        return /mac|iphone|ipad/i.test(platform) ? '⌘' : 'Ctrl+';
    };

    /**
     * Adds a close button to the title of a drawer panel
     * (wirecloud/component_sidebar template)
     *
     * @param {HTMLElement} panel
     * @param {Function} onclose
     */
    Industry.addDrawerCloseButton = function addDrawerCloseButton(panel, onclose) {
        const title = panel != null ? panel.querySelector('.panel-heading > .panel-title') : null;
        if (title == null || title.querySelector('.wc-drawer-close') != null) {
            return;
        }

        const close = new se.Button({
            class: 'btn-ghost btn-icon wc-drawer-close',
            iconClass: 'lc-icon lc-x',
            title: utils.gettext("Close")
        });
        close.addEventListener('click', onclose);
        close.insertInto(title);
    };

    Industry.utils = utils;
    Industry.se = se;

})(StyledElements, Wirecloud.Utils);
