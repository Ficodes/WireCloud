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

    const resolve_ui_class = function resolve_ui_class(name, defaultValue) {
        if (ns.registry != null) {
            return ns.registry.get(name, defaultValue);
        }
        return defaultValue;
    };

    ns.WorkspaceViewMenuItems = class WorkspaceViewMenuItems extends se.DynamicMenuItems {

        constructor(workspace) {
            super();

            Object.defineProperties(this, {
                workspace: {
                    value: workspace
                }
            });
        }

        /**
         * @override
         */
        build() {
            let item;

            const items = [];

            item = new se.MenuItem(utils.gettext("New workspace"), function () {
                (new Wirecloud.ui.NewWorkspaceWindowMenu()).show();
            }.bind(this.workspace));
            item.addIconClass("fas fa-plus");
            item.commandId = "new";
            items.push(item);

            item = new se.MenuItem(utils.gettext("Rename"), function () {
                (new Wirecloud.ui.RenameWindowMenu(this, utils.gettext('Rename Workspace'))).show();
            }.bind(this.workspace.model));
            item.addIconClass("fas fa-pencil-alt");
            item.commandId = "rename";
            item.commandLabel = utils.gettext("Rename workspace");
            item.setDisabled(!this.workspace.editing || !this.workspace.model.isAllowed('rename'));
            items.push(item);

            item = new se.MenuItem(utils.gettext("Share"), function () {
                const SharingWindowMenu = resolve_ui_class('SharingWindowMenu', Wirecloud.ui.SharingWindowMenu);
                (new SharingWindowMenu(this)).show();
            }.bind(this.workspace));
            item.addIconClass("fas fa-share");
            item.commandId = "share";
            item.commandLabel = utils.gettext("Share workspace");
            items.push(item);

            item = new se.MenuItem(utils.gettext("Upload to my resources"), function () {
                Wirecloud.UserInterfaceManager.views.marketplace.waitMarketListReady({
                    onComplete: function () {
                        var dialog = new Wirecloud.ui.PublishWorkspaceWindowMenu(this);
                        dialog.show();
                    }.bind(this)
                });
            }.bind(this.workspace.model));
            item.addIconClass("fas fa-archive");
            item.commandId = "upload";
            items.push(item);

            item = new se.MenuItem(utils.gettext("Embed"), function () {
                const EmbedCodeWindowMenu = resolve_ui_class('EmbedCodeWindowMenu', Wirecloud.ui.EmbedCodeWindowMenu);
                (new EmbedCodeWindowMenu(utils.gettext("Embed Code"), this)).show();
            }.bind(this.workspace));
            item.addIconClass("fas fa-code");
            item.commandId = "embed";
            item.commandLabel = utils.gettext("Embed workspace");
            items.push(item);

            item = new se.MenuItem(utils.gettext("Settings"), function () {
                this.showSettings();
            }.bind(this.workspace));
            item.addIconClass("fas fa-cog");
            item.commandId = "settings";
            item.commandLabel = utils.gettext("Workspace settings");
            item.setDisabled(!this.workspace.editing || !this.workspace.model.isAllowed('update_preferences'));
            items.push(item);

            item = new se.MenuItem(utils.gettext("Duplicate"), () => {
                (new Wirecloud.ui.NewWorkspaceWindowMenu({
                    title: utils.interpolate(utils.gettext("Copy of %(title)s"), this.workspace.model),
                    workspace: this.workspace.model.id
                })).show();
            });
            item.addIconClass("fas fa-clone");
            item.commandId = "duplicate";
            item.commandLabel = utils.gettext("Duplicate workspace");
            items.push(item);

            item = new se.MenuItem(utils.gettext("Remove"), () => {
                var dialog = new Wirecloud.ui.AlertWindowMenu(
                    utils.interpolate(utils.gettext('Do you really want to remove the "%(name)s" workspace?'), {
                        name: this.workspace.title
                    })
                );
                dialog.setHandler(() => {
                    return this.workspace.model.remove();
                }).show();
            });
            item.addIconClass("fas fa-trash");
            item.danger = true;
            item.commandId = "remove";
            item.commandLabel = utils.gettext("Remove workspace");
            item.setDisabled(!this.workspace.model.isAllowed('remove'));
            items.push(item);

            return items;
        }

    }

})(Wirecloud.ui, StyledElements, StyledElements.Utils);
