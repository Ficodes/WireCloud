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

const parent: string | null = null;

const BASE_CSS: string[] = [
    'css/fontawesome.min.css',
    'css/fontawesome-v4-shims.min.css',
    'css/base/utils.scss',
    'css/base/body.scss',
    'css/base/fade.css',
    'css/base/slide.scss',
    'css/base/code.scss',
    'css/base/z-depth.scss',
    'css/base/navigation.scss'
]

const CLASSIC_CORE_CSS: string[] = [
    'css/mac_search.scss',
    'css/screen_size_field.css',
    'css/mac_field.scss',
    'css/mac_selection_dialog.css'
]

const WORKSPACE_CSS: string[] = [
    'css/workspace/dragboard.scss',
    'css/workspace/operator.scss',
    'css/workspace/widget.scss',
    'css/workspace/modals/share.scss',
    'css/workspace/modals/upload.scss',
    'css/modals/upgrade_downgrade_component.scss',
    'css/modals/embed_code.scss'
]

const CATALOGUE_CSS: string[] = [
    'css/catalogue/emptyCatalogueBox.css',
    'css/catalogue/resource.scss',
    'css/catalogue/resource_details.scss',
    'css/catalogue/search_interface.scss',
    'css/catalogue/modals/upload.scss'
]

const PLATFORM_CORE_CSS: string[] = [
    'css/wirecloud_core.scss',
    'css/header.scss',
    'css/icons.css',
    'css/modals/base.scss',
    'css/modals/logs.scss'
]

const WIRING_EDITOR_CSS: string[] = [
    'css/wiring/layout.scss',
    'css/wiring/components.scss',
    'css/wiring/connection.scss',
    'css/wiring/behaviours.scss'
]

const TUTORIAL_CSS: string[] = [
    'css/tutorial.scss'
]

const STYLED_ELEMENTS_CSS: string[] = [
    'css/styled_elements_core.css',
    'css/styledelements/styled_addon.scss',
    'css/styledelements/styled_alternatives.scss',
    'css/styledelements/styled_container.css',
    'css/styledelements/styled_button.scss',
    'css/styledelements/styled_code_area.scss',
    'css/styledelements/styled_checkbox.css',
    'css/styledelements/styled_pills.scss',
    'css/styledelements/styled_notebook.scss',
    'css/styledelements/styled_form.css',
    'css/styledelements/styled_panel.scss',
    'css/styledelements/styled_numeric_field.scss',
    'css/styledelements/styled_text_field.scss',
    'css/styledelements/styled_text_area.scss',
    'css/styledelements/styled_password_field.scss',
    'css/styledelements/styled_select.scss',
    'css/styledelements/styled_border_layout.css',
    'css/styledelements/styled_horizontal_and_vertical_layout.scss',
    'css/styledelements/styled_file_field.scss',
    'css/styledelements/styled_table.scss',
    'css/styledelements/styled_label_badge.scss',
    'css/styledelements/styled_alert.scss',
    'css/styledelements/styled_rating.scss',
    'css/styledelements/styled_popup_menu.scss',
    'css/styledelements/styled_popover.scss',
    'css/styledelements/styled_tooltip.scss',
    'css/styledelements/styled_expander.scss',
    'css/styledelements/styled_offcanvas_layout.scss',
    'css/styledelements/styled_pagination.scss',
    'css/styledelements/styled_thumbnail.scss',
]

const get_platform_css = (view: string): string[] => {
    const common = [...BASE_CSS, ...STYLED_ELEMENTS_CSS];

    if (view === "classic" || view === "smartphone") {
        return [
            ...common,
            ...PLATFORM_CORE_CSS,
            ...WORKSPACE_CSS,
            ...CLASSIC_CORE_CSS,
            ...WIRING_EDITOR_CSS,
            ...CATALOGUE_CSS,
            ...TUTORIAL_CSS
        ];
    } else if (view === "embedded") {
        return [
            ...common,
            ...PLATFORM_CORE_CSS,
            ...WORKSPACE_CSS
        ];
    } else if (view === "widget") {
        return [
            "css/gadget.scss",
            ...BASE_CSS,
            ...STYLED_ELEMENTS_CSS
        ];
    } else {
        return [...common];
    }
};

export default {
    parent: parent,
    get_css: get_platform_css,
    get_scripts: (_: string): string[] => []
};