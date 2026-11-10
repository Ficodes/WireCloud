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


(function (Industry, se, utils) {

    "use strict";

    const PAGE_SIZE = 48;
    const VIEW_STORAGE_KEY = 'wirecloud.industry.resources-view';

    const TYPES = [
        {id: 'all', icon: 'boxes', label: () => utils.gettext("All")},
        {id: 'widget', icon: 'square-dashed', label: () => utils.gettext("Widgets")},
        {id: 'operator', icon: 'git-commit-horizontal', label: () => utils.gettext("Operators")},
        {id: 'mashup', icon: 'layers', label: () => utils.gettext("Mashups")}
    ];

    const TYPE_LABELS = {
        widget: () => utils.gettext("widget"),
        operator: () => utils.gettext("operator"),
        mashup: () => utils.gettext("mashup")
    };

    const normalize = function normalize(text) {
        return String(text == null ? '' : text).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
    };

    const read_view_preference = function read_view_preference() {
        try {
            return window.localStorage.getItem(VIEW_STORAGE_KEY) === 'table' ? 'table' : 'grid';
        } catch (e) {
            return 'grid';
        }
    };

    const write_view_preference = function write_view_preference(value) {
        try {
            window.localStorage.setItem(VIEW_STORAGE_KEY, value);
        } catch (e) {
            // Ignore storage errors
        }
    };

    const tag = function tag(type) {
        const element = Industry.element('span', 'tag wc-type-tag wc-type-' + type, [type in TYPE_LABELS ? TYPE_LABELS[type]() : type]);
        return element;
    };

    const endpoint_names = function endpoint_names(list) {
        return (list || []).map((endpoint) => endpoint.label || endpoint.name);
    };

    /**
     * Groups the installed components by vendor/name. Each group lists its
     * versions, newest first.
     */
    const collect_groups = function collect_groups() {
        const catalogue = Wirecloud.LocalCatalogue;
        return Object.keys(catalogue.resourceVersions || {}).map((groupId) => {
            const versions = catalogue.resourceVersions[groupId].slice().sort((a, b) => -a.version.compareTo(b.version));
            const latest = versions[0];
            return {
                id: groupId,
                versions: versions,
                latest: latest,
                type: latest.type,
                vendor: latest.vendor,
                title: latest.title,
                search: normalize([latest.title, latest.name, latest.vendor, latest.description].join(' '))
            };
        }).sort((a, b) => a.title.localeCompare(b.title));
    };

    /**
     * Number of instances of a component in the active workspace
     */
    const count_usage = function count_usage(group) {
        const workspace = Wirecloud.activeWorkspace;
        if (workspace == null) {
            return 0;
        }

        let components = [];
        if (group.type === 'widget') {
            components = workspace.widgets;
        } else if (group.type === 'operator') {
            components = workspace.operators;
        }
        return components.filter((component) => component.meta != null && component.meta.group_id === group.id).length;
    };

    const usage_label = function usage_label(count) {
        if (count === 0) {
            return utils.gettext("Not used here");
        }
        return utils.interpolate(utils.ngettext("%(count)s here", "%(count)s here", count), {count: count});
    };

    const get_editable_workspace_view = function get_editable_workspace_view() {
        const view = Wirecloud.UserInterfaceManager.views.workspace;
        if (view == null || view.model == null || !view.model.isAllowed('edit') || Industry.isAnonymous()) {
            return null;
        }
        return view;
    };

    const add_label = function add_label(type, long) {
        if (type === 'widget') {
            return long ? utils.gettext("Add to current tab") : utils.gettext("Add");
        } else if (type === 'operator') {
            return long ? utils.gettext("Add to wiring") : utils.gettext("Add");
        }
        return long ? utils.gettext("Create workspace") : utils.gettext("Use");
    };

    /**
     * Runs the main action of a component: add a widget to the current tab,
     * add an operator to the wiring or create a workspace from a mashup.
     */
    const add_component = function add_component(meta) {
        const uim = Wirecloud.UserInterfaceManager;

        if (meta.type === 'mashup') {
            uim.monitorTask(
                Wirecloud.createWorkspace({mashup: meta.uri}).then((workspace) => {
                    Industry.toast(utils.interpolate(utils.gettext("Created workspace “%(title)s”"), {title: workspace.title}));
                    return Wirecloud.changeActiveWorkspace(workspace);
                }, (error) => {
                    let dialog;
                    if (error != null && error.details != null && 'missingDependencies' in error.details) {
                        dialog = new Wirecloud.ui.MissingDependenciesWindowMenu(null, error.details);
                    } else {
                        dialog = new Wirecloud.ui.MessageWindowMenu(error, Wirecloud.constants.LOGGING.ERROR_MSG);
                    }
                    dialog.show();
                })
            );
            return;
        }

        const view = get_editable_workspace_view();
        if (view == null) {
            Industry.toast(utils.gettext("You cannot edit the current workspace"));
            return;
        }

        if (meta.type === 'widget') {
            uim.changeCurrentView('workspace');
            view.setEditing(true);
            view.activeTab.createWidget(meta).then(() => {
                Industry.toast(utils.interpolate(utils.gettext("Added “%(title)s” to %(tab)s"), {title: meta.title, tab: view.activeTab.title}));
            }, (error) => {
                Industry.toast(typeof error === 'string' ? error : utils.gettext("The widget could not be added"));
            });
        } else if (meta.type === 'operator') {
            Wirecloud.activeWorkspace.wiring.createOperator(meta).then(() => {
                uim.changeCurrentView('wiring');
                Industry.toast(utils.interpolate(utils.gettext("Added operator “%(title)s” to wiring"), {title: meta.title}));
            }, (error) => {
                Industry.toast(typeof error === 'string' ? error : utils.gettext("The operator could not be added"));
            });
        }
    };

    const build_preview = function build_preview(group) {
        const meta = group.latest;
        const preview = Industry.element('div', 'wc-resource-preview wc-resource-preview-' + group.type);
        preview.setAttribute('aria-hidden', 'true');

        if (group.type === 'operator') {
            const inputs = endpoint_names(meta.inputList);
            const outputs = endpoint_names(meta.outputList);
            preview.appendChild(Industry.element('span', 'mono', [
                (inputs.join(', ') || '∅') + '  →  ' + (outputs.join(', ') || '∅')
            ]));
        } else if (group.type === 'mashup') {
            for (let i = 0; i < 5; i++) {
                preview.appendChild(Industry.element('span', 'wc-resource-preview-cell'));
            }
        } else if (meta.image) {
            const image = document.createElement('img');
            image.alt = '';
            image.loading = 'lazy';
            image.src = meta.image;
            image.addEventListener('error', () => {
                image.remove();
                preview.classList.add('striped-placeholder', 'wc-resource-preview-missing');
                preview.appendChild(Industry.element('span', 'mono', [utils.gettext("widget preview")]));
            });
            preview.appendChild(image);
        } else {
            preview.classList.add('striped-placeholder', 'wc-resource-preview-missing');
            preview.appendChild(Industry.element('span', 'mono', [utils.gettext("widget preview")]));
        }

        return preview;
    };

    const build_add_button = function build_add_button(group, long) {
        const button = Industry.button({
            className: 'se-btn btn-ghost wc-resource-add',
            icon: 'plus',
            label: add_label(group.type, long)
        });
        const disabled = group.type !== 'mashup' && get_editable_workspace_view() == null;
        button.disabled = disabled;
        if (disabled) {
            button.title = utils.gettext("You cannot edit the current workspace");
        }
        button.addEventListener('click', (event) => {
            event.stopPropagation();
            add_component(group.latest);
        });
        return button;
    };

    // =========================================================================
    // Detail pane
    // =========================================================================

    const confirm_uninstall = function confirm_uninstall(details, allversions) {
        const myresources = Wirecloud.UserInterfaceManager.views.myresources;
        const message = allversions ?
            utils.interpolate(utils.gettext('Do you really want to uninstall all versions of "%(title)s"?'), {title: details.title}) :
            utils.interpolate(utils.gettext('Do you really want to uninstall "%(title)s" (version %(version)s)?'), {title: details.title, version: details.version.text});

        const dialog = new Wirecloud.ui.AlertWindowMenu(message);
        dialog.setHandler(() => {
            myresources.createUserCommand(allversions ? 'uninstallall' : 'uninstall', details, null)();
            Industry.toast(utils.interpolate(utils.gettext("Uninstalled %(title)s"), {title: details.title}));
        }).show();
    };

    const paint_detail = function paint_detail() {
        const pane = this.detailElement;
        pane.innerHTML = '';

        const group = this.groups.find((entry) => entry.id === this.selected);
        this.bodyElement.classList.toggle('wc-resources-with-detail', group != null);
        if (group == null) {
            pane.hidden = true;
            return;
        }
        pane.hidden = false;

        let meta = group.versions.find((version) => version.version.text === this.selectedVersion) || group.latest;

        const icon = Industry.blueprint(Industry.element('div', 'wc-resource-detail-icon'));
        if (meta.image && group.type === 'widget') {
            const image = document.createElement('img');
            image.alt = '';
            image.src = meta.image;
            image.addEventListener('error', () => image.remove());
            icon.appendChild(image);
        } else {
            icon.classList.add('striped-placeholder');
        }

        const close = Industry.button({
            className: 'se-btn btn-ghost btn-icon wc-resource-detail-close',
            icon: 'x',
            title: utils.gettext("Close"),
            onclick: () => this.select(null)
        });

        const heading = Industry.element('div', 'wc-resource-detail-heading', [
            Industry.element('div', 'wc-resource-detail-title', [meta.title]),
            Industry.element('div', 'wc-resource-detail-subtitle', [meta.vendor + ' · ' + (TYPE_LABELS[group.type] ? TYPE_LABELS[group.type]() : group.type)]),
            Industry.element('div', 'wc-resource-detail-uri mono', [meta.uri])
        ]);
        heading.querySelector('.wc-resource-detail-title').id = 'wc-resource-detail-title';
        pane.setAttribute('aria-labelledby', 'wc-resource-detail-title');
        pane.appendChild(Industry.element('div', 'wc-resource-detail-header', [icon, heading, close]));

        // Main action + version
        const primary = new se.Button({
            class: 'btn-primary wc-resource-detail-add',
            iconClass: 'lc-icon lc-plus',
            text: add_label(group.type, true)
        });
        primary.enabled = group.type === 'mashup' || get_editable_workspace_view() != null;
        primary.addEventListener('click', () => add_component(meta));

        const versions = new se.Select({
            initialValue: meta.version.text,
            initialEntries: group.versions.map((version) => ({label: 'v' + version.version.text, value: version.version.text}))
        });
        versions.addClassName('wc-resource-detail-version');
        versions.addEventListener('change', (select) => {
            this.selectedVersion = select.getValue();
            paint_detail.call(this);
        });
        const actions = Industry.element('div', 'wc-resource-detail-actions');
        primary.insertInto(actions);
        versions.insertInto(actions);
        pane.appendChild(actions);

        pane.appendChild(Industry.element('p', 'wc-resource-detail-description', [
            meta.description || utils.gettext("No description provided")
        ]));

        // Wiring endpoints
        const inputs = meta.inputList || [];
        const outputs = meta.outputList || [];
        if (inputs.length + outputs.length > 0) {
            const list = Industry.element('div', 'wc-resource-endpoints');
            inputs.forEach((endpoint) => {
                list.appendChild(Industry.element('div', 'wc-resource-endpoint', [
                    Industry.element('span', 'tag tag-neutral mono', [utils.gettext("in")]),
                    Industry.element('span', 'mono', [endpoint.label || endpoint.name])
                ]));
            });
            outputs.forEach((endpoint) => {
                list.appendChild(Industry.element('div', 'wc-resource-endpoint', [
                    Industry.element('span', 'tag tag-accent mono', [utils.gettext("out")]),
                    Industry.element('span', 'mono', [endpoint.label || endpoint.name])
                ]));
            });
            pane.appendChild(Industry.element('div', 'wc-resource-detail-section', [
                Industry.element('h6', null, [utils.gettext("Wiring endpoints")]),
                list
            ]));
        }

        // Usage in the current workspace
        const usage = count_usage(group);
        const usageContent = [Industry.element('h6', null, [utils.gettext("Used in")])];
        if (usage > 0 && Wirecloud.activeWorkspace != null) {
            usageContent.push(Industry.element('div', 'wc-resource-usage', [
                Industry.icon('layout-dashboard'),
                Industry.element('span', null, [
                    Wirecloud.activeWorkspace.owner + ' / ' + Wirecloud.activeWorkspace.title + ' (×' + usage + ')'
                ])
            ]));
        } else {
            usageContent.push(Industry.element('div', 'wc-resource-usage-empty', [utils.gettext("Not used in the current workspace.")]));
        }
        pane.appendChild(Industry.element('div', 'wc-resource-detail-section', usageContent));

        pane.appendChild(Industry.element('div', 'wc-resource-detail-spacer'));

        // Docs, details and uninstall
        const myresources = Wirecloud.UserInterfaceManager.views.myresources;
        const footer = Industry.element('div', 'wc-resource-detail-footer');
        footer.appendChild(Industry.button({
            className: 'se-btn wc-resource-docs',
            icon: 'file-text',
            label: utils.gettext("Docs"),
            onclick: () => {
                myresources.createUserCommand('showDetails', meta, {
                    version: meta.version.text,
                    tab: utils.gettext('Documentation')
                })();
            }
        }));
        footer.appendChild(Industry.element('div', 'wc-resource-detail-spacer'));

        const uninstall = Industry.button({
            className: 'se-btn btn-ghost wc-danger wc-resource-uninstall',
            icon: 'trash-2',
            label: utils.gettext("Uninstall")
        });
        uninstall.disabled = true;
        footer.appendChild(uninstall);
        pane.appendChild(footer);

        // Permissions and versions come from the resource details
        const requested = meta;
        Wirecloud.LocalCatalogue.getResourceDetails(meta.vendor, meta.name).then((details) => {
            if (this.selected !== group.id || meta !== requested || !uninstall.isConnected) {
                return;
            }
            details.changeVersion(meta.version.text);
            const allVersions = details.getAllVersions().length > 1 && details.isAllow('uninstall-all');
            if (!details.isAllow('uninstall') && !allVersions) {
                uninstall.hidden = true;
                return;
            }

            uninstall.disabled = false;
            if (!allVersions) {
                uninstall.addEventListener('click', () => confirm_uninstall(details, false));
                return;
            }

            const menu = new se.PopupMenu({placement: ['top-right', 'bottom-right']});
            menu.append(new se.MenuItem(utils.interpolate(utils.gettext("This version (v%(version)s)"), {version: meta.version.text}), () => confirm_uninstall(details, false)));
            const all = new se.MenuItem(utils.gettext("All versions"), () => confirm_uninstall(details, true));
            all.danger = true;
            menu.append(all);
            uninstall.addEventListener('click', () => menu.show(uninstall.getBoundingClientRect()));
        }, () => {
            uninstall.hidden = true;
        });
    };

    // =========================================================================
    // Results
    // =========================================================================

    const build_card = function build_card(group) {
        const meta = group.latest;
        const card = Industry.blueprint(Industry.element('div', 'wc-resource-card'));
        card.tabIndex = 0;
        card.setAttribute('role', 'listitem');
        card.dataset.id = group.id;
        card.classList.toggle('selected', this.selected === group.id);
        card.setAttribute('aria-current', this.selected === group.id ? 'true' : 'false');

        const usage = count_usage(group);
        const footer = Industry.element('div', 'wc-resource-card-footer', [
            Industry.element('span', 'wc-resource-usage-label', [usage_label(usage)]),
            build_add_button(group, false)
        ]);

        card.appendChild(build_preview(group));
        card.appendChild(Industry.element('div', 'wc-resource-card-body', [
            Industry.element('div', 'wc-resource-card-meta', [
                tag(group.type),
                Industry.element('span', 'mono wc-resource-version', ['v' + meta.version.text])
            ]),
            Industry.element('div', 'wc-resource-card-title', [meta.title]),
            Industry.element('div', 'wc-resource-card-vendor', [meta.vendor]),
            Industry.element('p', 'wc-resource-card-description', [meta.description || '']),
            footer
        ]));

        card.addEventListener('click', () => this.select(group.id));
        card.addEventListener('keydown', (event) => {
            if ((event.key === 'Enter' || event.key === ' ') && event.target === card) {
                event.preventDefault();
                this.select(group.id);
            }
        });
        return card;
    };

    const build_row = function build_row(group) {
        const meta = group.latest;
        const row = document.createElement('tr');
        row.tabIndex = 0;
        row.dataset.id = group.id;
        row.classList.toggle('selected', this.selected === group.id);

        const inputs = (meta.inputList || []).length;
        const outputs = (meta.outputList || []).length;
        const usage = count_usage(group);

        const cell = (children, className) => {
            const td = document.createElement('td');
            if (className) {
                td.className = className;
            }
            children.forEach((child) => td.appendChild(typeof child === 'string' ? document.createTextNode(child) : child));
            return td;
        };

        row.appendChild(cell([
            Industry.element('div', 'wc-resource-row-title', [meta.title]),
            Industry.element('div', 'wc-resource-row-vendor', [meta.vendor])
        ]));
        row.appendChild(cell([tag(group.type)]));
        row.appendChild(cell([meta.version.text], 'mono'));
        row.appendChild(cell([group.type === 'mashup' ? '—' : utils.interpolate(utils.gettext("%(inputs)s in · %(outputs)s out"), {inputs: inputs, outputs: outputs})], 'mono'));
        row.appendChild(cell([usage > 0 ? String(usage) : '—']));
        row.appendChild(cell([build_add_button(group, false)], 'text-right'));

        row.addEventListener('click', () => this.select(group.id));
        row.addEventListener('keydown', (event) => {
            if ((event.key === 'Enter' || event.key === ' ') && event.target === row) {
                event.preventDefault();
                this.select(group.id);
            }
        });
        return row;
    };

    const filter_groups = function filter_groups() {
        const words = normalize(this.query).split(/\s+/).filter((word) => word !== '');
        const base = this.groups.filter((group) => {
            return !this.excludedVendors.has(group.vendor) && words.every((word) => group.search.indexOf(word) !== -1);
        });
        const filtered = base.filter((group) => this.type === 'all' || group.type === this.type);
        return {base: base, filtered: filtered};
    };

    const paint_facets = function paint_facets(base) {
        this.typeFacets.innerHTML = '';
        TYPES.forEach((type) => {
            const count = base.filter((group) => type.id === 'all' || group.type === type.id).length;
            const button = Industry.button({
                className: 'wc-facet' + (this.type === type.id ? ' active' : ''),
                icon: type.icon,
                onclick: () => {
                    this.type = type.id;
                    this.limit = PAGE_SIZE;
                    paint.call(this);
                }
            });
            button.setAttribute('aria-pressed', this.type === type.id ? 'true' : 'false');
            button.appendChild(Industry.element('span', 'wc-facet-label', [type.label()]));
            button.appendChild(Industry.element('span', 'wc-facet-count', [String(count)]));
            this.typeFacets.appendChild(button);
        });

        const vendors = {};
        this.groups.forEach((group) => {
            vendors[group.vendor] = (vendors[group.vendor] || 0) + 1;
        });
        this.vendorFacets.innerHTML = '';
        Object.keys(vendors).sort((a, b) => vendors[b] - vendors[a] || a.localeCompare(b)).forEach((vendor) => {
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.checked = !this.excludedVendors.has(vendor);
            checkbox.addEventListener('change', () => {
                if (checkbox.checked) {
                    this.excludedVendors.delete(vendor);
                } else {
                    this.excludedVendors.add(vendor);
                }
                this.limit = PAGE_SIZE;
                paint.call(this);
            });
            this.vendorFacets.appendChild(Industry.element('label', 'wc-facet-vendor', [
                checkbox,
                Industry.element('span', 'wc-facet-label', [vendor]),
                Industry.element('span', 'wc-facet-count', [String(vendors[vendor])])
            ]));
        });
    };

    const paint = function paint() {
        const {base, filtered} = filter_groups.call(this);
        this.filtered = filtered;

        this.countElement.textContent = utils.interpolate(utils.gettext("%(shown)s of %(total)s components"), {
            shown: filtered.length,
            total: this.groups.length
        });

        paint_facets.call(this, base);

        this.viewButtons.forEach((button) => {
            const active = button.dataset.view === this.view;
            button.classList.toggle('active', active);
            button.setAttribute('aria-checked', active ? 'true' : 'false');
        });

        const results = this.resultsElement;
        const scrollTop = results.scrollTop;
        results.innerHTML = '';

        if (this.groups.length === 0) {
            results.appendChild(Industry.element('div', 'wc-resources-empty', [
                Industry.element('h4', null, [utils.gettext("Empty resource list")]),
                Industry.element('p', null, [utils.gettext("Currently, you do not have access to any component. You can get components using the Marketplace view or by uploading components manually using the Upload button.")])
            ]));
        } else if (filtered.length === 0) {
            results.appendChild(Industry.element('div', 'wc-resources-empty', [utils.gettext("No components match these filters.")]));
        } else {
            const visible = filtered.slice(0, this.limit);
            if (this.view === 'table') {
                const table = Industry.element('table', 'table wc-resources-table');
                const head = document.createElement('thead');
                const headRow = document.createElement('tr');
                [utils.gettext("Name"), utils.gettext("Type"), utils.gettext("Version"), utils.gettext("Endpoints"), utils.gettext("Used here"), ''].forEach((label) => {
                    headRow.appendChild(Industry.element('th', null, [label]));
                });
                head.appendChild(headRow);
                table.appendChild(head);
                const body = document.createElement('tbody');
                visible.forEach((group) => body.appendChild(build_row.call(this, group)));
                table.appendChild(body);
                results.appendChild(table);
            } else {
                const grid = Industry.element('div', 'wc-resources-grid');
                grid.setAttribute('role', 'list');
                visible.forEach((group) => grid.appendChild(build_card.call(this, group)));
                results.appendChild(grid);
            }

            if (filtered.length > this.limit) {
                const more = Industry.button({
                    className: 'se-btn wc-resources-more',
                    label: utils.interpolate(utils.gettext("Show more (%(count)s left)"), {count: filtered.length - this.limit}),
                    onclick: () => {
                        this.limit += PAGE_SIZE;
                        paint.call(this);
                    }
                });
                results.appendChild(more);
                observe_more.call(this, more);
            }
        }

        results.scrollTop = scrollTop;
        paint_detail.call(this);
    };

    // Incremental loading: show more results when the "Show more" button
    // becomes visible
    const observe_more = function observe_more(element) {
        if (typeof IntersectionObserver === 'undefined') {
            return;
        }
        if (this.observer == null) {
            this.observer = new IntersectionObserver((entries) => {
                if (entries.some((entry) => entry.isIntersecting)) {
                    this.observer.disconnect();
                    this.limit += PAGE_SIZE;
                    paint.call(this);
                }
            }, {root: this.resultsElement, rootMargin: '200px'});
        }
        this.observer.disconnect();
        this.observer.observe(element);
    };

    /**
     * "My resources" search view: facets, grid/table of results and a detail
     * pane. Registered as `MyResourcesSearchView`.
     */
    Industry.ResourcesView = class ResourcesView extends se.Alternative {

        constructor(id, options) {
            options = Object.assign({}, options, {class: 'wc-resources'});
            super(id, options);

            this.mainview = options.catalogue;
            this.groups = [];
            this.filtered = [];
            this.type = 'all';
            this.query = '';
            this.view = read_view_preference();
            this.excludedVendors = new Set();
            this.selected = null;
            this.selectedVersion = null;
            this.limit = PAGE_SIZE;
            this.outdated = true;
            this.initialized = false;

            // Compatibility with the platform search view API
            this.source = {refresh: () => this.refresh()};

            // Header
            this.countElement = Industry.element('span', 'wc-resources-count');
            this.searchInput = new se.TextField({
                class: 'wc-resources-search',
                placeholder: utils.gettext("Search name, vendor, description…")
            });
            this.searchInput.inputElement.setAttribute('aria-label', utils.gettext("Search components"));
            this.searchInput.addEventListener('change', () => {
                this.query = this.searchInput.getValue();
                this.limit = PAGE_SIZE;
                paint.call(this);
            });
            const search = Industry.element('div', 'wc-resources-search-field', [Industry.icon('search')]);
            this.searchInput.insertInto(search);

            const viewSwitch = Industry.element('div', 'seg wc-resources-view-switch');
            viewSwitch.setAttribute('role', 'radiogroup');
            viewSwitch.setAttribute('aria-label', utils.gettext("Results layout"));
            this.viewButtons = [['grid', 'layout-grid', utils.gettext("Grid")], ['table', 'list', utils.gettext("Table")]].map(([value, icon, label]) => {
                const button = Industry.button({
                    className: 'seg-opt',
                    icon: icon,
                    title: label,
                    onclick: () => {
                        this.view = value;
                        write_view_preference(value);
                        paint.call(this);
                    }
                });
                button.setAttribute('role', 'radio');
                button.dataset.view = value;
                viewSwitch.appendChild(button);
                return button;
            });

            const upload = Industry.button({
                className: 'se-btn wc-resources-upload',
                icon: 'upload',
                label: utils.gettext("Upload .wgt"),
                onclick: () => {
                    this.mainview.uploadButton.click();
                }
            });
            upload.hidden = Industry.isAnonymous();

            const title = Industry.element('h2', 'wc-resources-title', [utils.gettext("My resources")]);
            this.appendChild(Industry.element('header', 'wc-resources-header', [
                title,
                this.countElement,
                Industry.element('div', 'wc-resources-spacer'),
                search,
                viewSwitch,
                upload
            ]));

            // Facets
            this.typeFacets = Industry.element('div', 'wc-facet-list');
            this.vendorFacets = Industry.element('div', 'wc-facet-list wc-facet-vendors');
            const facets = Industry.element('aside', 'wc-resources-facets', [
                Industry.element('div', 'wc-facet-group', [Industry.element('h6', null, [utils.gettext("Type")]), this.typeFacets]),
                Industry.element('div', 'wc-facet-group', [Industry.element('h6', null, [utils.gettext("Vendor")]), this.vendorFacets])
            ]);
            facets.setAttribute('aria-label', utils.gettext("Filters"));

            this.resultsElement = Industry.element('div', 'wc-resources-results');
            this.resultsElement.setAttribute('aria-live', 'polite');
            this.detailElement = Industry.element('aside', 'wc-resources-detail');
            this.detailElement.hidden = true;

            this.bodyElement = Industry.element('div', 'wc-resources-body', [facets, this.resultsElement, this.detailElement]);
            this.appendChild(this.bodyElement);

            Wirecloud.LocalCatalogue.addEventListener('change', () => {
                this.outdated = true;
                if (this.initialized && !this.hidden) {
                    this.refresh();
                }
            });
            this.addEventListener('show', () => this.refresh_if_needed());
        }

        init() {
            this.initialized = true;
        }

        mark_outdated() {
            this.outdated = true;
        }

        refresh_if_needed() {
            // Usage counts depend on the active workspace, so always refresh
            this.refresh();
        }

        refresh() {
            this.outdated = false;
            this.groups = collect_groups();
            if (this.selected != null && !this.groups.some((group) => group.id === this.selected)) {
                this.selected = null;
            }
            paint.call(this);
            return this;
        }

        select(groupId) {
            if (groupId !== this.selected) {
                this.selectedVersion = null;
            }
            this.selected = groupId;
            this.resultsElement.querySelectorAll('[data-id]').forEach((element) => {
                const selected = element.dataset.id === groupId;
                element.classList.toggle('selected', selected);
                if (element.classList.contains('wc-resource-card')) {
                    element.setAttribute('aria-current', selected ? 'true' : 'false');
                }
            });
            paint_detail.call(this);
            return this;
        }

        handleKeydownEvent(key, modifiers) {
            if ((modifiers.ctrlKey || modifiers.metaKey) && key === "f") {
                this.searchInput.focus();
                return true;
            } else if (key === 'Escape' && this.selected != null) {
                this.select(null);
                return true;
            }
        }

        cancel() {
            if (this.selected != null) {
                this.select(null);
                return true;
            }
            return false;
        }

    };

    Industry.ResourcesView.prototype.view_name = 'search';

    /**
     * My resources view: Escape closes the detail pane
     */
    Industry.MyResourcesView = class MyResourcesView extends Wirecloud.ui.MyResourcesView {

        cancel() {
            const subview = this.alternatives.getCurrentAlternative();
            if (subview != null && typeof subview.cancel === 'function') {
                return subview.cancel();
            }
            return false;
        }

    };

    Wirecloud.ui.registry.register('MyResourcesSearchView', Industry.ResourcesView);
    Wirecloud.ui.registry.register('MyResourcesView', Industry.MyResourcesView);

})(Wirecloud.ui.Industry, StyledElements, Wirecloud.Utils);
