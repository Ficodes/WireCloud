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

// Industry: a root theme (it does not inherit from any other theme). Its
// stylesheets are written against the CSS custom properties defined in
// css/_tokens.scss, so the dark color scheme is only a variable swap.

const parent: string | null = null;

const BASE_CSS: string[] = [
    'css/base/fonts.scss',
    'css/base/root.scss',
    'css/base/reset.scss',
    'css/base/icons.scss'
];

// StyledElements
const COMPONENTS_CSS: string[] = [
    'css/components/layout.scss',
    'css/components/buttons.scss',
    'css/components/forms.scss',
    'css/components/menus.scss',
    'css/components/tabs.scss',
    'css/components/overlays.scss',
    'css/components/feedback.scss',
    'css/components/data.scss'
];

const SHELL_CSS: string[] = [
    'css/shell/loading.scss',
    'css/shell/app.scss',
    'css/shell/rail.scss',
    'css/shell/header.scss',
    'css/shell/statusbar.scss',
    'css/shell/palette.scss',
    'css/shell/toasts.scss'
];

const WORKSPACE_CSS: string[] = [
    'css/workspace/tabbar.scss',
    'css/workspace/dragboard.scss',
    'css/workspace/docks.scss',
    'css/workspace/widget.scss',
    'css/workspace/drawer.scss'
];

const WIRING_CSS: string[] = [
    'css/wiring/editor.scss',
    'css/wiring/components.scss',
    'css/wiring/connections.scss',
    'css/wiring/behaviours.scss'
];

const CATALOGUE_CSS: string[] = [
    'css/catalogue/resources.scss',
    'css/catalogue/search.scss',
    'css/catalogue/details.scss',
    'css/catalogue/macsearch.scss',
    'css/catalogue/upload.scss'
];

const MODALS_CSS: string[] = [
    'css/modals/dialog.scss',
    'css/modals/share.scss',
    'css/modals/forms.scss',
    'css/modals/admin.scss'
];

const TUTORIAL_CSS: string[] = [
    'css/tutorial.scss'
];

const PAGES_CSS: string[] = [
    'css/pages.scss'
];

const SHELL_SCRIPTS: string[] = [
    'js/industry/Icons.js',
    'js/industry/Toasts.js',
    'js/industry/CommandPalette.js',
    'js/industry/Header.js',
    'js/industry/Workspace.js',
    'js/industry/Wiring.js',
    'js/industry/Catalogue.js',
    'js/industry/Init.js'
];

const get_css = (view: string): string[] => {
    const common = [...BASE_CSS, ...COMPONENTS_CSS];

    if (view === "classic" || view === "smartphone") {
        return [
            ...common,
            ...SHELL_CSS,
            ...WORKSPACE_CSS,
            ...WIRING_CSS,
            ...CATALOGUE_CSS,
            ...MODALS_CSS,
            ...TUTORIAL_CSS,
            ...PAGES_CSS
        ];
    } else if (view === "embedded") {
        return [
            ...common,
            'css/shell/loading.scss',
            'css/shell/app.scss',
            'css/shell/toasts.scss',
            ...WORKSPACE_CSS,
            ...MODALS_CSS
        ];
    } else if (view === "widget") {
        // Widgets get a small token based stylesheet so they inherit fonts
        // and colors, plus the StyledElements styles (widgets can use them
        // through the widget API)
        return [...common, 'css/gadget.scss'];
    } else {
        // index: login and error pages
        return [...common, ...PAGES_CSS];
    }
};

const get_scripts = (view: string): string[] => {
    if (view === "classic" || view === "smartphone" || view === "embedded") {
        return SHELL_SCRIPTS;
    }
    return [];
};

export default {
    parent: parent,
    get_css: get_css,
    get_scripts: get_scripts
};
