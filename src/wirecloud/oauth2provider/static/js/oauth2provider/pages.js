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

/* globals StyledElements */
(function (se) {
    "use strict";

    const replace = function replace(original, element) {
        original.parentElement.insertBefore(element, original);
        original.remove();
    };

    const moveContents = function moveContents(original, container) {
        Array.from(original.childNodes).forEach(function (child) {
            original.removeChild(child);
            container.appendChild(child);
        });
    };

    const enhance = function enhance(root) {
        root.querySelectorAll('[data-se-panel]').forEach(function (original) {
            const panel = new se.Panel({class: 'oauth-panel'});
            const title = original.querySelector('[data-se-panel-title]');
            const body = original.querySelector('[data-se-panel-body]');
            const footer = original.querySelector('[data-se-panel-footer]');
            if (title) {
                panel.setTitle(title);
                panel.get().setAttribute('role', 'region');
                panel.get().setAttribute('aria-labelledby', title.id);
            }
            if (body) {
                moveContents(body, panel.body);
            }
            if (footer) {
                const actions = new se.Container({class: 'panel-footer'});
                moveContents(footer, actions);
                actions.insertInto(panel.get());
            }
            replace(original, panel.get());
        });

        root.querySelectorAll('[data-se-alert]').forEach(function (original) {
            const message = new se.Container();
            moveContents(original, message);
            const alert = new se.Alert({state: original.getAttribute('data-se-alert'), message: message});
            alert.get().setAttribute('role', 'note');
            replace(original, alert.get());
        });

        root.querySelectorAll('button[data-se-button]').forEach(function (original) {
            const form = original.form;
            const button = new se.Button({text: original.textContent.trim(), usedInForm: true,
                state: original.getAttribute('data-se-button')});
            const element = button.get();
            element.setAttribute('type', 'submit');
            element.setAttribute('name', original.getAttribute('name'));
            element.setAttribute('value', original.getAttribute('value'));
            if (original.hasAttribute('aria-label')) {
                element.setAttribute('aria-label', original.getAttribute('aria-label'));
            }
            // StyledElements consumes click events. Native requestSubmit keeps the
            // chosen button's name/value, hidden CSRF fields, and browser redirect flow.
            button.addEventListener('click', function () {
                form.requestSubmit(element);
            });
            replace(original, element);
        });
    };

    se.OAuthPages = {enhance: enhance};
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { enhance(document); }, {once: true});
    } else {
        enhance(document);
    }
})(StyledElements);
