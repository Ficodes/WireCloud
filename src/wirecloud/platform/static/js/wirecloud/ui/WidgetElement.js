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

(function () {

    'use strict';

    class Widget extends HTMLElement {
        constructor() {
            super();
            this.hasShadowDOM = false;
            this.loadedURL = "";
            this.baseURL = "";
        }

        connectedCallback() {
            this.style.width = '100%';
            this.style.height = '100%';
            this.style.display = 'block';

            if (!this.hasShadowDOM) {
                this.attachShadow({mode: 'open'});
                this.hasShadowDOM = true;
            }
        }

        disconnectedCallback() {
            this._unload();
        }

        /**
         * Opts this custom element into state-preserving DOM moves. Without
         * this callback, browsers invoke disconnectedCallback() followed by
         * connectedCallback() even when an ancestor is moved atomically with
         * moveBefore(). disconnectedCallback() unloads the widget and clears
         * its shadow root, so changing between dock and grid layouts would
         * otherwise leave version 2 widgets blank.
         */
        connectedMoveCallback() {}

        load(codeurl, baseurl) {
            if (!this.hasShadowDOM) {
                throw new Error('Cannot load widget: widget is not attached to the DOM');
            }

            this._unload();

            this.codeurl = codeurl;
            this.baseURL = baseurl;

            // Load the widget code
            Wirecloud.io.makeRequest(codeurl, {
                method: 'GET'
            }).then((response) => {
                if (response.status === 200) {
                    const contentType = response.transport.getResponseHeader('Content-Type') || '';
                    if (contentType.indexOf('text/html') === -1) {
                        throw new Error('Error loading widget: non-HTML content type');
                    }

                    this.loadedURL = codeurl;

                    // Load the widget code into the shadow DOM
                    this._handleHTMLResponse(response.responseText);

                    // Dispatch onload event
                    this.dispatchEvent(new Event('load'));
                } else {
                    // Maybe show an error screen in the shadow DOM?
                    throw new Error('Error loading widget (HTTP ' + response.status + '): ' + response.statusText);
                }
            }).catch((error) => {
                throw new Error('Error loading widget: ' + error.message);
            });
        }

        _unload() {
            if (!this.hasShadowDOM) {
                return;
            }

            // Clean the shadow DOM
            this.shadowRoot.innerHTML = '';

            // Dispatch onunload event
            this.dispatchEvent(new Event('unload'));
        }

        _handleHTMLResponse(text) {
            const dom = new DOMParser().parseFromString(text, 'text/html');
            const headElements = [];

            // Add all stylesheets to the headElements array (which will be in the shadow root), as the DOMParser
            // always puts them in the head
            Array.from(dom.head.querySelectorAll('link, script, style')).forEach((node) => {
                headElements.push(node);
            });

            // List of attributes that can contain relative URLs
            const ATTR_LIST = ["href", "src", "background", "action", "data", "formaction", "icon", "poster", "usemap"];

            // Walk the DOM tree and replace all relative URLs with absolute ones
            const walk = (node, walkChildren = true) => {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    ATTR_LIST.forEach((attr) => {
                        if (node.hasAttribute(attr)) {
                            const url = new URL(node.getAttribute(attr), this.baseURL);
                            node.setAttribute(attr, url.href);
                        }
                    });

                    // Additionally, handle srcset attribute
                    if (node.hasAttribute('srcset')) {
                        const srcset = node.getAttribute('srcset').split(',').map((src) => {
                            const [url, size] = src.trim().split(' ');
                            const absolute_url = new URL(url, this.baseURL);
                            return `${absolute_url.href} ${size}`;
                        }).join(', ');
                        node.setAttribute('srcset', srcset);
                    }
                }

                if (walkChildren) {
                    node.childNodes.forEach(walk);
                }
            };

            walk(dom.body);

            // Add the widget code to the shadow DOM
            headElements.forEach((node) => {
                walk(node);
                this.shadowRoot.appendChild(node);
            });
            this.shadowRoot.appendChild(dom.body);
        }
    };

    window.customElements.define('wirecloud-widget', Widget);

})();
