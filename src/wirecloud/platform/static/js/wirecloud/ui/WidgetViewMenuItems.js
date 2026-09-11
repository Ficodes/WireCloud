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


(function (ns, se, utils) {

    "use strict";

    ns.WidgetViewMenuItems = class WidgetViewMenuItems extends se.DynamicMenuItems {

        constructor(widget) {
            super();

            Object.defineProperties(this, {
                widget: {
                    value: widget
                }
            });
        }

        /**
         * @override
         */
        build() {
            let item;

            const items = [];

            item = new se.MenuItem(utils.gettext("Rename"), () => {
                this.widget.titleelement.enableEdition();
            });
            item.addIconClass("fas fa-pencil-alt");
            item.setDisabled(!this.widget.model.isAllowed('rename', 'editor'));
            items.push(item);

            item = new se.MenuItem(utils.gettext("Reload"), () => {
                this.widget.reload();
            });
            item.addIconClass("fas fa-sync");
            item.setDisabled(this.widget.model.missing);
            items.push(item);

            item = new se.MenuItem(utils.gettext("Upgrade/Downgrade"), () => {
                const dialog = new Wirecloud.ui.UpgradeWindowMenu(this.widget.model);
                dialog.show();
            });
            item.addIconClass("fas fa-retweet");
            item.setDisabled(!this.widget.model.isAllowed('upgrade', 'editor') || !Wirecloud.LocalCatalogue.hasAlternativeVersion(this.widget.model.meta));
            items.push(item);

            item = new se.MenuItem(utils.gettext("Logs"), () => {
                this.widget.showLogs();
            });
            item.addIconClass("fas fa-tags");
            items.push(item);

            item = new se.MenuItem(utils.gettext("Settings"), () => {
                this.widget.showSettings();
            });
            item.addIconClass("fas fa-cog");
            item.setDisabled(!this.widget.model.hasPreferences() || !this.widget.model.isAllowed('configure', 'editor'));
            items.push(item);

            item = new se.MenuItem(utils.gettext("User's Manual"), () => {
                const myresources_view = Wirecloud.UserInterfaceManager.views.myresources;
                myresources_view.createUserCommand('showDetails', this.widget.model.meta, {
                    version: this.widget.model.meta.version,
                    tab: utils.gettext('Documentation')
                })();
            });
            item.addIconClass("fas fa-book");
            item.setDisabled(this.widget.model.meta.doc === '');
            items.push(item);

            items.push(new StyledElements.Separator());

            const fulldragboard = !!(this.widget.layout && this.widget.layout.fulldragboard);

            item = new se.MenuItem(
                fulldragboard ? utils.gettext("Exit Full Dragboard") : utils.gettext("Full Dragboard"),
                () => {
                    this.widget.setFullDragboardMode(!fulldragboard, true);
                }
            );
            item.addIconClass(fulldragboard ? "fas fa-compress" : "fas fa-expand");
            item.setDisabled(!this.widget.model.isAllowed('move', 'editor'));
            items.push(item);

            if (fulldragboard) {
                // Other options require exiting first from the full dragboard mode
                return items;
            }

            item = new se.MenuItem(utils.gettext("Hide for this screen size"), () => {
                this.widget.hideInCurrentScreenSize();
            });
            item.addIconClass("fas fa-eye-slash");
            items.push(item);

            const othertabs = this.widget.tab.workspace.tabs.filter((tab) => tab.id !== this.widget.tab.id);
            const movesubmenu = new se.SubMenuItem(utils.gettext("Move to tab"), {iconClass: 'fas fa-arrow-right'});
            movesubmenu.setDisabled(othertabs.length === 0 || !this.widget.model.isAllowed('move', 'editor'));
            othertabs.forEach((tab) => {
                movesubmenu.append(new se.MenuItem(tab.title, () => {
                    this.widget.moveToTab(tab);
                }));
            });
            items.push(movesubmenu);

            return items;
        }

    }

})(Wirecloud.ui, StyledElements, StyledElements.Utils);
