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

// Applies the last color scheme chosen in WireCloud before painting, on pages
// whose CSP blocks inline scripts (the OAuth consent and connections pages).
// Loaded as a standalone, blocking script: it is not part of any bundle.
// Keep in sync with the inline copy in templates/wirecloud/views/_head.html
// and with Wirecloud.ui.ColorScheme.

(function () {

    "use strict";

    let scheme = null;
    try {
        scheme = window.localStorage.getItem("wirecloud.color-scheme");
    } catch (e) {
        // Storage not available: follow the system color scheme
    }
    if (scheme === "light" || scheme === "dark") {
        document.documentElement.setAttribute("data-wc-color-scheme", scheme);
    }

})();
