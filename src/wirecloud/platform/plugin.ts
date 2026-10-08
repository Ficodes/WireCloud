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

// TODO Commons' and catalogue's files are here too, that SHOULD not be that way, but the order matters and maintaining the
// order between modules is too much work. This is a temporary solution. In the future, files should import
// each other instead of excepting something to have been executed before.

const WIRING_EDITOR_FILES: string[] = [
    'js/wirecloud/ui/WiringEditor.js',
    'js/wirecloud/ui/WiringEditor/Behaviour.js',
    'js/wirecloud/ui/WiringEditor/BehaviourPrefs.js',
    'js/wirecloud/ui/WiringEditor/BehaviourEngine.js',
    'js/wirecloud/ui/WiringEditor/Endpoint.js',
    'js/wirecloud/ui/WiringEditor/EndpointGroup.js',
    'js/wirecloud/ui/WiringEditor/Component.js',
    'js/wirecloud/ui/WiringEditor/ComponentPrefs.js',
    'js/wirecloud/ui/WiringEditor/ComponentGroup.js',
    'js/wirecloud/ui/WiringEditor/ComponentShowcase.js',
    'js/wirecloud/ui/WiringEditor/ComponentDraggable.js',
    'js/wirecloud/ui/WiringEditor/ComponentDraggablePrefs.js',
    'js/wirecloud/ui/WiringEditor/Connection.js',
    'js/wirecloud/ui/WiringEditor/ConnectionPrefs.js',
    'js/wirecloud/ui/WiringEditor/ConnectionHandle.js',
    'js/wirecloud/ui/WiringEditor/ConnectionEngine.js',
    'js/wirecloud/ui/WiringEditor/KeywordSuggestion.js',
]

const WIRECLOUD_API_FILES: string[] = [
    'js/WirecloudAPI/WirecloudAPIBootstrap.js',
    'js/WirecloudAPI/WirecloudWidgetAPI.js',
    'js/WirecloudAPI/WirecloudOperatorAPI.js',
    'js/WirecloudAPI/WirecloudAPICommon.js',
    'js/WirecloudAPI/StyledElements.js',
    'js/WirecloudAPI/ComponentManagementAPI.js',
    'js/WirecloudAPI/DashboardManagementAPI.js',
    'js/WirecloudAPI/WirecloudAPIClosure.js',
    'js/WirecloudAPI/WirecloudAPIV2Bootstrap.js'
]

const TUTORIAL_FILES: string[] = [
    'js/wirecloud/ui/Tutorial.js',
    'js/wirecloud/ui/Tutorial/Utils.js',
    'js/wirecloud/ui/TutorialCatalogue.js',
    'js/wirecloud/ui/TutorialSubMenu.js',
    'js/wirecloud/ui/Tutorial/PopUp.js',
    'js/wirecloud/ui/Tutorial/SimpleDescription.js',
    'js/wirecloud/ui/Tutorial/UserAction.js',
    'js/wirecloud/ui/Tutorial/FormAction.js',
    'js/wirecloud/ui/Tutorial/AutoAction.js',
    'js/wirecloud/Tutorials/BasicConcepts.js',
    'js/wirecloud/Tutorials/BehaviourOrientedWiring.js',
]

const SHIM_FILES: string[] = [
    'js/wirecloud/shims/classList.js',
]

const STYLED_ELEMENTS_FILES: string[] = [
    'js/StyledElements/Utils.js',
    'js/StyledElements/ObjectWithEvents.js',
    'js/StyledElements/StyledElements.js',
    'js/StyledElements/InputElement.js',
    'js/StyledElements/CommandQueue.js',
    'js/StyledElements/Container.js',
    'js/StyledElements/Accordion.js',
    'js/StyledElements/Expander.js',
    'js/StyledElements/Fragment.js',
    'js/StyledElements/PaginatedSource.js',
    'js/StyledElements/GUIBuilder.js',
    'js/StyledElements/Tooltip.js',
    'js/StyledElements/Addon.js',
    'js/StyledElements/Button.js',
    'js/StyledElements/FileButton.js',
    'js/StyledElements/PopupMenuBase.js',
    'js/StyledElements/PopupMenu.js',
    'js/StyledElements/DynamicMenuItems.js',
    'js/StyledElements/MenuItem.js',
    'js/StyledElements/Separator.js',
    'js/StyledElements/SubMenuItem.js',
    'js/StyledElements/PopupButton.js',
    'js/StyledElements/StaticPaginatedSource.js',
    'js/StyledElements/FileField.js',
    'js/StyledElements/NumericField.js',
    'js/StyledElements/TextField.js',
    'js/StyledElements/TextArea.js',
    'js/StyledElements/CodeArea.js',
    'js/StyledElements/List.js',
    'js/StyledElements/PasswordField.js',
    'js/StyledElements/Select.js',
    'js/StyledElements/ToggleButton.js',
    'js/StyledElements/Pills.js',
    'js/StyledElements/Tab.js',
    'js/StyledElements/Notebook.js',
    'js/StyledElements/Alternative.js',
    'js/StyledElements/Alternatives.js',
    'js/StyledElements/HorizontalLayout.js',
    'js/StyledElements/VerticalLayout.js',
    'js/StyledElements/BorderLayout.js',
    'js/StyledElements/ModelTable.js',
    'js/StyledElements/EditableElement.js',
    'js/StyledElements/HiddenField.js',
    'js/StyledElements/ButtonsGroup.js',
    'js/StyledElements/CheckBox.js',
    'js/StyledElements/RadioButton.js',
    'js/StyledElements/InputInterface.js',
    'js/StyledElements/TextInputInterface.js',
    'js/StyledElements/InputInterfaces.js',
    'js/StyledElements/MultivaluedInputInterface.js',
    'js/wirecloud/ui/ParametrizableValueInputInterface.js',
    'js/wirecloud/ui/ParametrizedTextInputInterface.js',
    'js/wirecloud/ui/ScreenSizesInputInterface.js',
    'js/StyledElements/VersionInputInterface.js',
    'js/StyledElements/InputInterfaceFactory.js',
    'js/StyledElements/DefaultInputInterfaceFactory.js',
    'js/StyledElements/Form.js',
    'js/StyledElements/PaginationInterface.js',
    'js/StyledElements/Popover.js',
    'js/StyledElements/Panel.js',
    'js/StyledElements/OffCanvasLayout.js',
    'js/StyledElements/Alert.js',
    'js/StyledElements/Typeahead.js',
]

const get_scripts: (view: string) => string[] = (view: string): string[] => {
    const common = [...SHIM_FILES,
            'js/StyledElements/Utils.js',
            'js/wirecloud/Utils.js',
            'js/wirecloud/BaseRequirements.js',
            'js/common/ComputedStyle.js',
            'js/wirecloud/constants.js',
            'js/StyledElements/Event.js',
            'js/StyledElements/ObjectWithEvents.js',
            'js/wirecloud/core.js',
            'js/wirecloud/UserInterfaceManager.js',
            'js/wirecloud/Task.js',
            'js/wirecloud/io.js',
            'js/wirecloud/ContextManager.js',
            'js/wirecloud/PreferenceDoesNotExistError.js',
            'js/wirecloud/UserPrefDef.js',
            'js/wirecloud/UserPref.js',
            'js/wirecloud/PersistentVariable.js',
            'js/wirecloud/PersistentVariableDef.js',
            'js/wirecloud/PolicyManager.js',
            'js/wirecloud/HistoryManager.js',
            'js/wirecloud/Version.js',
            'js/wirecloud/MashableApplicationComponent.js',
            'js/wirecloud/WidgetMeta.js',
            'js/wirecloud/PreferenceDef.js',
            'js/wirecloud/PlatformPref.js',
            'js/wirecloud/PreferencesDef.js',
            'js/wirecloud/PlatformPreferencesDef.js',
            'js/wirecloud/WorkspacePreferencesDef.js',
            'js/wirecloud/TabPreferencesDef.js',
        ...STYLED_ELEMENTS_FILES,
                     'js/wirecloud/WorkspaceTab.js',
                     'js/wirecloud/Workspace.js',
                     'js/wirecloud/Preferences.js',
                     'js/wirecloud/PlatformPreferences.js',
                     'js/wirecloud/PreferenceManager.js',
                     'js/wirecloud/WorkspacePreferences.js',
                     'js/wirecloud/TabPreferences.js',
                     'js/wirecloud/PropertyCommiter.js',
                     'js/wirecloud/LogManager.js',
                     'js/wirecloud/Widget.js',
                     'js/wirecloud/Wiring.js',
                     'js/wirecloud/ui/MACField.js',
                     'js/wirecloud/ui/InputInterfaceFactory.js',
                     'js/wirecloud/ui/WidgetView.js',
                     'js/wirecloud/ui/WidgetElement.js',
                     'js/wirecloud/ui/WidgetViewMenuItems.js',
                     'js/wirecloud/ui/Draggable.js',
                     'js/wirecloud/ui/Theme.js',
                     'js/wirecloud/WirecloudCatalogue.js',
                     'js/wirecloud/WirecloudCatalogue/ResourceDetails.js',
                     'js/wirecloud/LocalCatalogue.js',
                     'js/wirecloud/WorkspaceCatalogue.js',
                     'js/wirecloud/wiring/Connection.js',
                     'js/wirecloud/wiring/Endpoint.js',
                     'js/wirecloud/wiring/EndpointDoesNotExistError.js',
                     'js/wirecloud/wiring/EndpointTypeError.js',
                     'js/wirecloud/wiring/EndpointValueError.js',
                     'js/wirecloud/wiring/SourceEndpoint.js',
                     'js/wirecloud/wiring/TargetEndpoint.js',
                     'js/wirecloud/wiring/MissingEndpoint.js',
                     'js/wirecloud/wiring/Operator.js',
                     'js/wirecloud/wiring/OperatorMeta.js',
                     'js/wirecloud/wiring/OperatorSourceEndpoint.js',
                     'js/wirecloud/wiring/OperatorTargetEndpoint.js',
                     'js/wirecloud/wiring/WidgetSourceEndpoint.js',
                     'js/wirecloud/wiring/WidgetTargetEndpoint.js',
                     'js/wirecloud/wiring/KeywordSuggestion.js',
        ...WIRECLOUD_API_FILES];

    if (view === "classic" || view === "embedded" || view === "smartphone") {
        const scripts = [
            ...common,
                'js/wirecloud/ui/WorkspaceListItems.js',
                'js/wirecloud/ui/WorkspaceViewMenuItems.js',
                'js/wirecloud/ui/MACSearch.js',
                'js/wirecloud/ui/ComponentSidebar.js',
                'js/wirecloud/ui/WorkspaceView.js',
                'js/wirecloud/ui/WorkspaceTabView.js',
                'js/wirecloud/ui/WorkspaceTabViewMenuItems.js',
                'js/wirecloud/vendor/gridstack.js',
                'js/wirecloud/ui/SidebarLayout.js',
                'js/wirecloud/ui/WorkspaceTabViewDragboard.js',
                'js/wirecloud/ui/MyResourcesView.js',
                'js/wirecloud/ui/MarketplaceView.js',
                'js/wirecloud/ui/CatalogueSearchView.js',
                'js/wirecloud/ui/CatalogueView.js',
                'js/wirecloud/MarketManager.js',
                'js/wirecloud/ui/MarketplaceViewMenuItems.js',
                'js/wirecloud/ui/ResourcePainter.js',
                'js/wirecloud/ui/WindowMenu.js',
                'js/wirecloud/ui/WirecloudCatalogue/UploadWindowMenu.js',
                'js/wirecloud/ui/WirecloudCatalogue/ResourceDetailsView.js',
                'js/wirecloud/ui/AlertWindowMenu.js',
                'js/wirecloud/ui/HTMLWindowMenu.js',
                'js/wirecloud/Widget/PreferencesWindowMenu.js',
                'js/wirecloud/ui/MissingDependenciesWindowMenu.js',
                'js/wirecloud/ui/FormWindowMenu.js',
                'js/wirecloud/ui/LogWindowMenu.js',
                'js/wirecloud/ui/EmbedCodeWindowMenu.js',
                'js/wirecloud/ui/SharingWindowMenu.js',
                'js/wirecloud/ui/MACSelectionWindowMenu.js',
                'js/wirecloud/ui/MessageWindowMenu.js',
                'js/wirecloud/ui/NewWorkspaceWindowMenu.js',
                'js/wirecloud/ui/ParametrizeWindowMenu.js',
                'js/wirecloud/ui/PreferencesWindowMenu.js',
                'js/wirecloud/ui/AdminPanelWindowMenu.js',
                'js/wirecloud/ui/UserManagementWindowMenu.js',
                'js/wirecloud/ui/OperatorPreferencesWindowMenu.js',
                'js/wirecloud/ui/PublishWorkspaceWindowMenu.js',
                'js/wirecloud/ui/PublishResourceWindowMenu.js',
                'js/wirecloud/ui/RenameWindowMenu.js',
                'js/wirecloud/ui/UpgradeWindowMenu.js',
                'js/wirecloud/ui/UserTypeahead.js',
                'js/wirecloud/ui/UserGroupTypeahead.js',
            ...WIRING_EDITOR_FILES,
            ...TUTORIAL_FILES
        ];

        if (view !== "embedded") {
            scripts.push('js/wirecloud/ui/WirecloudHeader.js');
        }

        return scripts;
    } else if (view === "widget") {
        // TODO Actually include correct files, maybe they should be the base files and other be imported
        // depending on the requested features
        return [
            'js/WirecloudAPI/WirecloudAPIBootstrap.js',
            'js/WirecloudAPI/WirecloudWidgetAPI.js',
            'js/WirecloudAPI/WirecloudAPICommon.js'
        ];
    } else if (view === "bootstrap") {
        return [
            'js/StyledElements/Utils.js',
            'js/wirecloud/Utils.js'
        ];
    } else if (view === "operator") {
        return [
            'js/WirecloudAPI/WirecloudAPIBootstrap.js',
            'js/WirecloudAPI/WirecloudOperatorAPI.js',
            'js/WirecloudAPI/WirecloudAPICommon.js',
            'js/WirecloudAPI/WirecloudAPIClosure.js',
        ];
    } else {
        return common;
    }
};

export default {
    get_scripts: get_scripts,
    scripts_location: 'js'
}
