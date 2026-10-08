# -*- coding: utf-8 -*-
# Copyright (c) 2026 Future Internet Consulting and Development Solutions S.L.

# This file is part of Wirecloud.

# Wirecloud is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Wirecloud is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with Wirecloud.  If not, see <http://www.gnu.org/licenses/>.

widget_instance_data = [
    {
        "id": "67af66aa3ac952bc88cc1a63-0-0",
        "title": "string",
        "widget": "vendor/name/version",
        "layouts": {
            "0": {
                "x": 0,
                "y": 0,
                "w": 1,
                "h": 1,
                "minimized": False,
                "titlevisible": True,
                "fulldragboard": False,
                "visible": True
            }
        },
        "read_only": False,
        "permissions": {
            "editor": {
                "close": None,
                "configure": None,
                "move": None,
                "rename": None,
                "resize": None,
                "minimize": None,
                "upgrade": None
            },
            "viewer": {
                "close": None,
                "configure": None,
                "move": None,
                "rename": None,
                "resize": None,
                "minimize": None,
                "upgrade": None
            }
        },
        "variable_values": None,
        "preferences": {
            "input_label_pref": {
                "name": "input_label_pref",
                "secure": False,
                "readonly": False,
                "hidden": False,
                "value": "Keywords"
            },
            "input_placeholder_pref": {
                "name": "input_placeholder_pref",
                "secure": False,
                "readonly": False,
                "hidden": False,
                "value": "Text to send..."
            },
            "button_label_pref": {
                "name": "button_label_pref",
                "secure": False,
                "readonly": False,
                "hidden": False,
                "value": "Send"
            }
        },
        "properties": {}
    },
    {
        "id": "67af66aa3ac952bc88cc1a63-0-1",
        "title": "string",
        "widget": "vendor/name/version",
        "layouts": {
            "0": {
                "x": 0,
                "y": 0,
                "w": 1,
                "h": 1,
                "minimized": False,
                "titlevisible": True,
                "fulldragboard": False,
                "visible": True
            }
        },
        "read_only": False,
        "permissions": {
            "editor": {
                "close": None,
                "configure": None,
                "move": None,
                "rename": None,
                "resize": None,
                "minimize": None,
                "upgrade": None
            },
            "viewer": {
                "close": None,
                "configure": None,
                "move": None,
                "rename": None,
                "resize": None,
                "minimize": None,
                "upgrade": None
            }
        },
        "variable_values": None,
        "preferences": {
            "input_label_pref": {
                "name": "input_label_pref",
                "secure": False,
                "readonly": False,
                "hidden": False,
                "value": "Keywords"
            },
            "input_placeholder_pref": {
                "name": "input_placeholder_pref",
                "secure": False,
                "readonly": False,
                "hidden": False,
                "value": "Text to send..."
            },
            "button_label_pref": {
                "name": "button_label_pref",
                "secure": False,
                "readonly": False,
                "hidden": False,
                "value": "Send"
            }
        },
        "properties": {}
    }
]
# GET /workspace/{workspace_id}/tab/{tab_id}/widget_instances/
get_widget_instance_collection_summary = "Get all widget instances in a tab"
get_widget_instance_collection_description = "Gets all widget instances in a tab"
get_widget_instance_collection_response_description = "List of widget instances"
get_widget_instance_collection_auth_required_response_description = "Authentication required"
get_widget_instance_collection_permission_denied_response_description = "Permission denied"
get_widget_instance_collection_not_found_response_description = "Workspace or Tab not found"
get_widget_instance_collection_workspace_id_description = "Workspace identifier"
get_widget_instance_collection_tab_id_description = "Tab identifier"
get_widget_instance_collection_response_example = widget_instance_data

# POST /workspace/{workspace_id}/tab/{tab_id}/widget_instances/
create_widget_instance_collection_summary = "Create a new widget instance"
create_widget_instance_collection_description = "Creates a new widget instance"
create_widget_instance_collection_response_description = "Widget instance created"
create_widget_instance_collection_auth_required_response_description = "Authentication required"
create_widget_instance_collection_permission_denied_response_description = "Permission denied"
create_widget_instance_collection_not_found_response_description = "Workspace or Tab not found"
create_widget_instance_collection_validation_error_response_description = "Validation error"
create_widget_instance_collection_not_acceptable_response_description = "Invalid request content type"
create_widget_instance_collection_workspace_id_description = "Workspace identifier"
create_widget_instance_collection_tab_id_description = "Tab identifier"
create_widget_instance_collection_widget_instance_description = "Widget instance data"
create_widget_instance_collection_widget_instance_example = {
    "title": "widget instance",
    "widget": "vendor/name/version",
    "layouts": {
        "0": {
            "x": 0,
            "y": 0,
            "w": 1,
            "h": 1,
            "minimized": False,
            "titlevisible": True,
            "fulldragboard": False,
            "visible": True
        }
    },
    "read_only": False,
    "permissions": {},
    "variable_values": {}
}
create_widget_instance_collection_response_example = widget_instance_data

# POST /workspace/{workspace_id}/tab/{tab_id}/widget_instances/
update_widget_instance_collection_summary = "Update a widget instance or widget instances"
update_widget_instance_collection_description = "Updates a widget instance or widget instances"
update_widget_instance_collection_response_description = "Widget instance(s) updated"
update_widget_instance_collection_auth_required_response_description = "Authentication required"
update_widget_instance_collection_permission_denied_response_description = "Permission denied"
update_widget_instance_collection_not_found_response_description = "Workspace or Tab not found"
update_widget_instance_collection_validation_error_response_description = "Validation error"
update_widget_instance_collection_bad_request_response_description = "Missing or invalid data was provided"
update_widget_instance_collection_workspace_id_description = "Workspace identifier"
update_widget_instance_collection_tab_id_description = "Tab identifier"
update_widget_instance_collection_widget_instance_description = "Widget instance data"
update_widget_instance_collection_widget_instance_example = [{
    "id": "6834371a9c236eb656c30789-0-0",
    "tab": "6834371a9c236eb656c30789-0",
    "layouts": {
        "0": {
            "x": 0,
            "y": 0,
            "w": 1,
            "h": 1,
            "minimized": False,
            "titlevisible": True,
            "fulldragboard": False,
            "visible": True
        },
        "1": None
    },
    "title": "new-name-for-widget instance",
    "widget": "vendor/name/version",
    "move": False
}]

# GET /workspace/{workspace_id}/tab/{tab_id}/widget_instances/{iwidget_id}
get_widget_instance_entry_summary = "Get a widget instance"
get_widget_instance_entry_description = "Gets a widget instance"
get_widget_instance_entry_response_description = "Widget instance information"
get_widget_instance_entry_auth_required_response_description = "Authentication required"
get_widget_instance_entry_permission_denied_response_description = "Permission denied"
get_widget_instance_entry_not_found_response_description = "Workspace, Tab or widget instance not found"
get_widget_instance_entry_workspace_id_description = "Workspace identifier"
get_widget_instance_entry_tab_id_description = "Tab identifier"
get_widget_instance_entry_widget_instance_id_description = "Widget instance identifier"
get_widget_instance_entry_response_example = widget_instance_data

# POST /workspace/{workspace_id}/tab/{tab_id}/widget_instances/{iwidget_id}
update_widget_instance_entry_summary = "Update a widget instance"
update_widget_instance_entry_description = "Updates a widget instance"
update_widget_instance_entry_response_description = "widget instance updated"
update_widget_instance_entry_auth_required_response_description = "Authentication required"
update_widget_instance_entry_permission_denied_response_description = "Permission denied"
update_widget_instance_entry_not_found_response_description = "Workspace, Tab or widget instance not found"
update_widget_instance_entry_validation_error_response_description = "Validation error"
update_widget_instance_entry_bad_request_response_description = "Missing or invalid data was provided"
update_widget_instance_entry_workspace_id_description = "Workspace identifier"
update_widget_instance_entry_tab_id_description = "Tab identifier"
update_widget_instance_entry_widget_instance_id_description = "Widget instance identifier"
update_widget_instance_entry_widget_instance_description = "Widget instance data"
update_widget_instance_entry_widget_instance_example = {
    "tab": "6834371a9c236eb656c30789-0",
    "layouts": {
        "0": {
            "x": 0,
            "y": 0,
            "w": 1,
            "h": 1,
            "minimized": False,
            "titlevisible": True,
            "fulldragboard": False,
            "visible": True
        },
        "1": None
    },
    "title": "new-name-for-widget-instance",
    "widget": "vendor/name/version",
    "move": False
}

# DELETE /workspace/{workspace_id}/tab/{tab_id}/widget_instances/{iwidget_id}
delete_widget_instance_entry_summary = "Delete a widget instance"
delete_widget_instance_entry_description = "Deletes a widget instance"
delete_widget_instance_entry_response_description = "Widget instance deleted"
delete_widget_instance_entry_auth_required_response_description = "Authentication required"
delete_widget_instance_entry_permission_denied_response_description = "Permission denied"
delete_widget_instance_entry_not_found_response_description = "Workspace, Tab or widget instance not found"
delete_widget_instance_entry_workspace_id_description = "Workspace identifier"
delete_widget_instance_entry_tab_id_description = "Tab identifier"
delete_widget_instance_entry_widget_instance_id_description = "Widget instance identifier"

# POST /workspace/{workspace_id}/tab/{tab_id}/widget_instances/{iwidget_id}/preferences
update_widget_instance_preferences_summary = "Update a widget instance preference"
update_widget_instance_preferences_description = "Updates widget instance preferences"
update_widget_instance_preferences_response_description = "Widget instance preferences updated"
update_widget_instance_preferences_auth_required_response_description = "Authentication required"
update_widget_instance_preferences_permission_denied_response_description = "Permission denied"
update_widget_instance_preferences_not_found_response_description = "Workspace, Tab, widget instance or Resource not found"
update_widget_instance_preferences_validation_error_response_description = "Validation error"
update_widget_instance_preferences_bad_request_response_description = "Missing or invalid data was provided"
update_widget_instance_preferences_workspace_id_description = "Workspace identifier"
update_widget_instance_preferences_tab_id_description = "Tab identifier"
update_widget_instance_preferences_widget_instance_id_description = "Widget instance identifier"
update_widget_instance_preferences_new_values_description = "New values for widget instance preferences"
update_widget_instance_preferences_new_values_example = {
    "pref1": 2,
    "pref2": "string",
}

# GET /workspace/{workspace_id}/tab/{tab_id}/widget_instances/{iwidget_id}/preferences
get_widget_instance_preferences_summary = "Get widget instance preferences"
get_widget_instance_preferences_description = "Gets widget instance preferences"
get_widget_instance_preferences_response_description = "Widget instance preferences"
get_widget_instance_preferences_auth_required_response_description = "Authentication required"
get_widget_instance_preferences_permission_denied_response_description = "Permission denied"
get_widget_instance_preferences_not_found_response_description = "Workspace, Tab, widget instance or Resource not found"
get_widget_instance_preferences_workspace_id_description = "Workspace identifier"
get_widget_instance_preferences_tab_id_description = "Tab identifier"
get_widget_instance_preferences_widget_instance_id_description = "Widget instance identifier"
get_widget_instance_preferences_response_example = {
    "pref1": 2,
    "pref2": "string",
}

# POST /workspace/{workspace_id}/tab/{tab_id}/widget_instances/{iwidget_id}/properties
update_widget_instance_properties_summary = "Update widget instance properties"
update_widget_instance_properties_description = "Updates widget instance properties"
update_widget_instance_properties_response_description = "Widget instance properties updated"
update_widget_instance_properties_auth_required_response_description = "Authentication required"
update_widget_instance_properties_permission_denied_response_description = "Permission denied"
update_widget_instance_properties_not_found_response_description = "Workspace, Tab, widget instance or Resource not found"
update_widget_instance_properties_validation_error_response_description = "Validation error"
update_widget_instance_properties_bad_request_response_description = "Missing or invalid data was provided"
update_widget_instance_properties_workspace_id_description = "Workspace identifier"
update_widget_instance_properties_tab_id_description = "Tab identifier"
update_widget_instance_properties_widget_instance_id_description = "Widget instance identifier"
update_widget_instance_properties_new_values_description = "New values for widget instance properties"
update_widget_instance_properties_new_values_example = {
    "name-prop": "new-value-for-prop"
}

# GET /workspace/{workspace_id}/tab/{tab_id}/widget_instances/{iwidget_id}/properties
get_widget_instance_properties_summary = "Get widget instance properties"
get_widget_instance_properties_description = "Gets widget instance properties"
get_widget_instance_properties_response_description = "Widget instance properties"
get_widget_instance_properties_auth_required_response_description = "Authentication required"
get_widget_instance_properties_permission_denied_response_description = "Permission denied"
get_widget_instance_properties_not_found_response_description = "Workspace, Tab, widget instance or Resource not found"
get_widget_instance_properties_workspace_id_description = "Workspace identifier"
get_widget_instance_properties_tab_id_description = "Tab identifier"
get_widget_instance_properties_widget_instance_id_description = "Widget instance identifier"
get_widget_instance_properties_response_example = {
    "name-prop": "new-value-for-prop"
}
