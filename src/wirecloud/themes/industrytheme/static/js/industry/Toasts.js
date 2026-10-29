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

    const DURATION = 4500;

    let container = null;
    let timeout = null;
    let current = null;

    const get_container = function get_container() {
        if (container == null || !container.isConnected) {
            container = document.createElement('div');
            container.className = 'wc-toast-region';
            container.setAttribute('role', 'status');
            container.setAttribute('aria-live', 'polite');
            document.body.appendChild(container);
        }
        return container;
    };

    const hide = function hide() {
        clearTimeout(timeout);
        timeout = null;
        if (current != null) {
            const toast = current;
            current = null;
            toast.element.classList.remove('in');
            setTimeout(() => toast.element.remove(), 200);
            if (typeof toast.onclose === 'function') {
                toast.onclose();
            }
        }
    };

    /**
     * Shows a toast message at the bottom of the page. Only one toast is
     * displayed at a time.
     *
     * @param {String} message
     * @param {Object} [options]
     * @param {String} [options.actionLabel] label of the optional action button
     * @param {Function} [options.action] callback of the action button
     * @param {Function} [options.onclose] called when the toast is dismissed
     *   (by timeout, by another toast or after the action)
     * @param {Number} [options.duration] milliseconds (default: 4500)
     * @returns {Object} toast handler with a `hide` method
     */
    Industry.toast = function toast(message, options) {
        options = options || {};
        hide();

        const element = Industry.element('div', 'wc-toast', [
            Industry.element('span', 'wc-toast-message', [message])
        ]);

        if (options.actionLabel && typeof options.action === 'function') {
            const button = Industry.button({
                className: 'wc-toast-action',
                label: options.actionLabel,
                onclick: () => {
                    const handler = current;
                    if (handler != null) {
                        handler.onclose = null;
                    }
                    hide();
                    options.action();
                }
            });
            element.appendChild(button);
        }

        get_container().appendChild(element);
        // Trigger the transition
        window.requestAnimationFrame(() => element.classList.add('in'));

        current = {element: element, onclose: options.onclose};
        timeout = setTimeout(hide, options.duration || DURATION);

        return {
            hide: () => {
                if (current != null && current.element === element) {
                    hide();
                }
            }
        };
    };

    Industry.hideToast = hide;

})(Wirecloud.ui.Industry, Wirecloud.Utils);
