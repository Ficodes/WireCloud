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

workspace_data = {
    "id": "67af66aa3ac952bc88cc1a63",
    "name": "workspace-1",
    "title": "Workspace 1",
    "public": False,
    "shared": False,
    "requireauth": False,
    "owner": "admin",
    "removable": True,
    "lastmodified": 1739544564357,
    "description": "",
    "longdescription": "",
    "preferences": {
        "public": {
            "inherit": False,
            "value": "false"
        },
        "requireauth": {
            "inherit": False,
            "value": "false"
        },
        "sharelist": {
            "inherit": False,
            "value": "[]"
        },
        "screenSizes": {
            "inherit": False,
            "value": "[{\"id\": 0, \"name\": \"Phone\", \"moreOrEqual\": 0, \"lessOrEqual\": 767, \"columns\": 1}, {\"id\": 1, \"name\": \"Tablet\", \"moreOrEqual\": 768, \"lessOrEqual\": 1199, \"columns\": 6}, {\"id\": 2, \"name\": \"Desktop\", \"moreOrEqual\": 1200, \"lessOrEqual\": -1, \"columns\": 12}]"
        },
        "cellheight": {
            "inherit": False,
            "value": "40"
        },
        "margin": {
            "inherit": False,
            "value": "5"
        }
    },
    "users": [
        {
            "fullname": "Pepe Lopez",
            "username": "admin",
            "organization": False,
            "accesslevel": "owner"
        }
    ],
    "groups": [],
    "empty_params": [],
    "extra_prefs": [],
    "wiring": {
        "version": "2.0",
        "connections": [],
        "operators": {},
        "visualdescription": {
            "behaviours": [],
            "components": {
                "widget": {},
                "operator": {}
            },
            "connections": []
        }
    },
    "tabs": [
        {
            "id": "67af66aa3ac952bc88cc1a63-0",
            "name": "tab",
            "title": "Tab",
            "visible": True,
            "widgets": [],
            "preferences": {
                "requireauth": {
                    "inherit": True,
                    "value": "false"
                },
                "sharelist": {
                    "inherit": True,
                    "value": "[]"
                },
                "screenSizes": {
                    "inherit": True,
                    "value": "[{\"id\": 0, \"name\": \"Phone\", \"moreOrEqual\": 0, \"lessOrEqual\": 767, \"columns\": 1}, {\"id\": 1, \"name\": \"Tablet\", \"moreOrEqual\": 768, \"lessOrEqual\": 1199, \"columns\": 6}, {\"id\": 2, \"name\": \"Desktop\", \"moreOrEqual\": 1200, \"lessOrEqual\": -1, \"columns\": 12}]"
                },
                "cellheight": {
                    "inherit": True,
                    "value": "40"
                },
                "margin": {
                    "inherit": True,
                    "value": "5"
                }
            },
            "last_modified": 1739959520701
        },
        {
            "last_modified": 1739959520701
        }
    ]
}

tab_data = {
    "id": "67af66aa3ac952bc88cc1a63-2",
    "name": "tab-1",
    "title": "Tab 1",
    "visible": False,
    "widgets": [],
    "preferences": {
        "requireauth": {
            "inherit": True,
            "value": "false"
        },
        "sharelist": {
            "inherit": True,
            "value": "[]"
        },
        "screenSizes": {
            "inherit": True,
            "value": "[{\"id\": 0, \"name\": \"Phone\", \"moreOrEqual\": 0, \"lessOrEqual\": 767, \"columns\": 1}, {\"id\": 1, \"name\": \"Tablet\", \"moreOrEqual\": 768, \"lessOrEqual\": 1199, \"columns\": 6}, {\"id\": 2, \"name\": \"Desktop\", \"moreOrEqual\": 1200, \"lessOrEqual\": -1, \"columns\": 12}]"
        },
        "cellheight": {
            "inherit": True,
            "value": "40"
        },
        "margin": {
            "inherit": True,
            "value": "5"
        }
    },
    "last_modified": 1739962053890
}

# GET /workspaces/
get_workspace_collection_summary = "Get the list of available workspaces"
get_workspace_collection_description = "Get the list of available workspaces for the current user."
get_workspace_collection_response_description = "List of available workspaces"
get_workspace_collection_auth_required_response_description = "Authentication required"
get_workspace_collection_response_example = [
    {
        "id": "67af66aa3ac952bc88cc1a63",
        "name": "workspace-1",
        "title": "Workspace 1",
        "public": False,
        "shared": False,
        "requireauth": False,
        "owner": "admin",
        "removable": True,
        "lastmodified": 1739544564357,
        "description": "",
        "longdescription": ""
    },
    {
        "id": "67af690990fa2feddb2c6ce8",
        "name": "workspace-2",
        "title": "Workspace 2",
        "public": False,
        "shared": False,
        "requireauth": False,
        "owner": "admin",
        "removable": True,
        "lastmodified": 1739545223259,
        "description": "",
        "longdescription": ""
    }
]

# POST /workspaces/
create_workspace_collection_summary = "Create a new workspace"
create_workspace_collection_description = "Creates a new workspace."
create_workspace_collection_workspace_description = "Workspace creation data"
create_workspace_collection_response_description = "Workspace created"
create_workspace_collection_auth_required_response_description = "Authentication required"
create_workspace_collection_permission_denied_response_description = "Permission denied"
create_workspace_collection_not_acceptable_response_description = "Invalid request content type"
create_workspace_collection_conflict_response_description = "A workspace with the given name already exists"
create_workspace_collection_validation_error_response_description = "Validation error"
create_workspace_collection_workspace_example = [
    {
        "name": "workspace-1",
        "title": "Workspace 1",
        "workspace": "",
        "mashup": "",
        "preferences": {},
        "allow_renaming": False,
        "dry_run": False
    },

    {
        "name": "workspace-2",
        "title": "Workspace 2",
        "workspace": "67af690990fa2feddb2c6ce8",
        "mashup": "",
        "preferences": {
            "preference1": "value1",
            "preference2": {"inherit": True, "value": "value2"}
        },
        "allow_renaming": False,
        "dry_run": False
    },

    {
        "name": "workspace-3",
        "title": "Workspace 3",
        "workspace": "",
        "mashup": "vendor/name/version",
        "preferences": {},
        "allow_renaming": False,
        "dry_run": False
    }

]
create_workspace_collection_response_example = {
    "id": "67b4b5ed26cda64e5e8484aa",
    "name": "workspace-1",
    "title": "Workspace 1",
    "public": False,
    "shared": False,
    "requireauth": False,
    "owner": "admin",
    "removable": True,
    "lastmodified": 1739896280119,
    "description": "",
    "longdescription": "",
    "preferences": {
        "public": {
            "inherit": False,
            "value": "false"
        },
        "requireauth": {
            "inherit": False,
            "value": "false"
        },
        "sharelist": {
            "inherit": False,
            "value": "[]"
        },
        "screenSizes": {
            "inherit": False,
            "value": "[{\"id\": 0, \"name\": \"Phone\", \"moreOrEqual\": 0, \"lessOrEqual\": 767, \"columns\": 1}, {\"id\": 1, \"name\": \"Tablet\", \"moreOrEqual\": 768, \"lessOrEqual\": 1199, \"columns\": 6}, {\"id\": 2, \"name\": \"Desktop\", \"moreOrEqual\": 1200, \"lessOrEqual\": -1, \"columns\": 12}]"
        },
        "cellheight": {
            "inherit": False,
            "value": "40"
        },
        "margin": {
            "inherit": False,
            "value": "5"
        }
    },
    "users": [
        {
            "fullname": "Pepe Lopez",
            "username": "username",
            "organization": False,
            "accesslevel": "owner"
        }
    ],
    "groups": [],
    "empty_params": [],
    "extra_prefs": [],
    "wiring": {
        "version": "2.0",
        "connections": [],
        "operators": {},
        "visualdescription": {
            "behaviours": [],
            "components": {
                "widget": {},
                "operator": {}
            },
            "connections": []
        }
    },
    "tabs": [
        {
            "id": "67b4b5ed26cda64e5e8484aa-0",
            "name": "tab",
            "title": "Tab",
            "visible": True,
            "widgets": [],
            "preferences": {
                "requireauth": {
                    "inherit": True,
                    "value": "false"
                },
                "sharelist": {
                    "inherit": True,
                    "value": "[]"
                },
                "screenSizes": {
                    "inherit": True,
                    "value": "[{\"id\": 0, \"name\": \"Phone\", \"moreOrEqual\": 0, \"lessOrEqual\": 767, \"columns\": 1}, {\"id\": 1, \"name\": \"Tablet\", \"moreOrEqual\": 768, \"lessOrEqual\": 1199, \"columns\": 6}, {\"id\": 2, \"name\": \"Desktop\", \"moreOrEqual\": 1200, \"lessOrEqual\": -1, \"columns\": 12}]"
                },
                "cellheight": {
                    "inherit": True,
                    "value": "40"
                },
                "margin": {
                    "inherit": True,
                    "value": "5"
                }
            },
            "last_modified": 1739896280315
        }
    ]
}

# GET /workspaces/{workspace_id}
get_workspace_entry_id_summary = "Get workspace information"
get_workspace_entry_id_description = "Get information about a workspace with id."
get_workspace_entry_id_response_description = "Workspace information"
get_workspace_entry_id_permission_denied_response_description = "Permission denied"
get_workspace_entry_id_not_found_response_description = "Workspace not found"
get_workspace_entry_id_workspace_id_description = "Workspace identifier"
get_workspace_entry_id_response_example = workspace_data

# GET /workspace/{owner}/{name}/
get_workspace_entry_owner_name_summary = "Get workspace information"
get_workspace_entry_owner_name_description = "Get information about a workspace with the workspace name and the owner."
get_workspace_entry_owner_name_response_description = "Workspace information"
get_workspace_entry_owner_name_permission_denied_response_description = "Permission denied"
get_workspace_entry_owner_name_not_found_response_description = "Workspace not found"
get_workspace_entry_owner_name_owner_description = "Workspace owner"
get_workspace_entry_owner_name_name_description = "Workspace name"
get_workspace_entry_owner_name_response_example = workspace_data

# POST /workspace/{workspace_id}/
update_workspace_entry_summary = "Update workspace information"
update_workspace_entry_description = "Update information about a workspace with id."
update_workspace_entry_response_description = "Workspace information updated"
update_workspace_entry_auth_required_response_description = "Authentication required"
update_workspace_entry_permission_denied_response_description = "Permission denied"
update_workspace_entry_not_acceptable_response_description = "Invalid request content type"
update_workspace_entry_not_found_response_description = "Workspace not found"
update_workspace_entry_workspace_entry_description = "Workspace entry data"
update_workspace_entry_workspace_id_description = "Workspace identifier"
update_workspace_entry_workspace_entry_example = {
    "name": "workspace-2",
    "title": "Workspace 2",
    "description": "Description",
    "longdescription": "Long description"
}
update_workspace_entry_conflict_response_description = "A workspace with the given name already exists"

# DELETE /workspace/{workspace_id}/
delete_workspace_entry_summary = "Delete a workspace"
delete_workspace_entry_description = "Deletes a workspace with id."
delete_workspace_entry_response_description = "Workspace deleted"
delete_workspace_entry_auth_required_response_description = "Authentication required"
delete_workspace_entry_permission_denied_response_description = "Permission denied"
delete_workspace_entry_not_found_response_description = "Workspace not found"
delete_workspace_entry_workspace_id_description = "Workspace identifier"

# POST /workspace/{workspace_id}/tabs/
create_tab_collection_summary = "Create a new tab"
create_tab_collection_description = "Creates a new tab."
create_tab_collection_response_description = "Tab created"
create_tab_collection_tab_create_description = "Tab creation data"
create_tab_collection_auth_required_response_description = "Authentication required"
create_tab_collection_permission_denied_response_description = "Permission denied"
create_tab_collection_not_acceptable_response_description = "Invalid request content type"
create_tab_collection_conflict_response_description = "Tab already exists with the given name"
create_tab_collection_not_found_response_description = "Workspace not found"
create_tab_collection_workspace_id_description = "Workspace identifier"
create_tab_collection_validation_error_response_description = "Validation error"
create_tab_collection_tab_create_example = [
    {
        "name": "tab",
        "title": "Tab",
        "description": "Description",
        "longdescription": "Long description"
    },
    {
        "name": "tab2",
        "title": "",
        "description": "Description",
        "longdescription": "Long description"
    }
]
create_tab_collection_response_example = tab_data

# GET /workspace/{workspace_id}/tab/{tab_id}/
get_tab_entry_summary = "Get tab information"
get_tab_entry_description = "Get information about a tab."
get_tab_entry_response_description = "Tab information"
get_tab_entry_not_found_response_description = "Workspace or Tab not found"
get_tab_entry_permission_denied_response_description = "Permission denied"
get_tab_entry_workspace_id_description = "Workspace identifier"
get_tab_entry_tab_id_description = "Tab identifier"
get_tab_entry_response_example = tab_data

# POST /workspace/{workspace_id}/tab/{tab_id}/
update_tab_entry_summary = "Update tab information"
update_tab_entry_description = "Update information about a tab."
update_tab_entry_response_description = "Tab information updated"
update_tab_entry_tab_create_entry_description = "Tab creation data"
update_tab_entry_auth_required_response_description = "Authentication required"
update_tab_entry_permission_denied_response_description = "Permission denied"
update_tab_entry_not_found_response_description = "Workspace or Tab not found"
update_tab_entry_conflict_response_description = "A tab with the given name already exists"
update_tab_entry_not_acceptable_response_description = "Invalid request content type"
update_tab_entry_workspace_id_description = "Workspace identifier"
update_tab_entry_tab_id_description = "Tab identifier"
update_tab_entry_tab_create_entry_example = {
    "name": "tab-2",
    "title": "Tab 2",
    "visible": True,
}

# DELETE /workspace/{workspace_id}/tab/{tab_id}/
delete_tab_entry_summary = "Delete a tab"
delete_tab_entry_description = "Deletes a tab."
delete_tab_entry_response_description = "Tab deleted"
delete_tab_entry_auth_required_response_description = "Authentication required"
delete_tab_entry_permission_denied_response_description = "Permission denied"
delete_tab_entry_not_found_response_description = "Workspace or Tab not found"
delete_tab_entry_workspace_id_description = "Workspace identifier"
delete_tab_entry_tab_id_description = "Tab identifier"

# POST /workspace/{to_ws_id}/merge
process_mashup_merge_service_summary = "Merge workspaces"
process_mashup_merge_service_description = "Merge the content of a workspace into another one."
process_mashup_merge_service_response_description = "Workspace merged"
process_mashup_merge_service_mashup_merge_service_description = "Mashup merge data"
process_mashup_merge_service_auth_required_response_description = "Authentication required"
process_mashup_merge_service_permission_denied_response_description = "Permission denied"
process_mashup_merge_service_not_acceptable_response_description = "Invalid request content type"
process_mashup_merge_service_not_found_response_description = "Workspace not found"
process_mashup_merge_service_validation_error_response_description = "Validation error"
process_mashup_merge_service_to_ws_id_description = "Mashup identifier to do the merge"
process_mashup_merge_service_mashup_merge_service_example = [
    {
        "workspace": "67af690990fa2feddb2c6ce8",
        "mashup": ""
    },
    {
        "workspace": "",
        "mashup": "vendor/name/version"
    }
]

# POST /workspace/{workspace_id}/publish/
process_publish_service_summary = "Publish workspace"
process_publish_service_description = "Publish a workspace in a market."
process_publish_service_response_description = "Workspace published"
process_publish_service_json_data_description = "Workspace publication data"
process_publish_service_bad_request_response_description = "Missing or invalid data was provided"
process_publish_service_auth_required_response_description = "Authentication required"
process_publish_service_not_acceptable_response_description = "Invalid request content type"
process_publish_service_permission_denied_response_description = "Permission denied"
process_publish_service_not_found_response_description = "Workspace not found"
process_publish_service_workspace_id_description = "Workspace identifier"
process_publish_service_image_file_description = "Image file"
process_publish_service_smartphoneimage_file_description = "Smartphone image file"
process_publish_service_json_data_example = {
    "type": "mashup",
    "macversion": 1,
    "name": "workspace-1",
    "vendor": "api",
    "version": "1.0",
    "title": "Workspace 1",
    "description": "Temporal mashup for the workspace copy operation",
    "longdescription": "A long description",
    "email": "a@example.com",
    "homepage": "",
    "doc": "",
    "changelog": "",
    "image": "",
    "smartphoneimage": "",
    "license": "",
    "licenseurl": "",
    "issuetracker": "",
    "authors": [],
    "contributors": [],
    "requirements": [],
    "default_lang": "en",
    "translations": {},
    "translation_index_usage": {},
    "preferences": {},
    "params": [],
    "tabs": [],
    "embedmacs": False,
    "embedded": [],
    "wiring": {
        "inputs": [],
        "outputs": [],
        "version": "2.0",
        "connections": [],
        "operators": {},
        "visualdescription": {
            "behaviours": [],
            "components": {
                "widget": {},
                "operator": {}
            },
            "connections": []
        }
    },
    "readOnlyWidgets": False,
    "parametrization": {},
    "readOnlyConnectables": False
}
process_publish_service_response_example = {
    "type": "mashup",
    "macversion": 1,
    "name": "workspace-1",
    "vendor": "api",
    "version": "1.0",
    "title": "Workspace 1",
    "description": "Temporal mashup for the workspace copy operation",
    "longdescription": "DESCRIPTION.md",
    "email": "a@example.com",
    "homepage": "",
    "doc": "",
    "changelog": "",
    "image": "http://127.0.0.1:8000/catalogue/media/api/workspace-1/1.0/images/catalogue.png",
    "smartphoneimage": "http://127.0.0.1:8000/catalogue/media/api/workspace-1/1.0/images/smartphone.png",
    "license": "",
    "licenseurl": "",
    "issuetracker": "",
    "authors": [
        {
            "name": "admin",
            "email": "null",
            "url": "null"
        }
    ],
    "contributors": [],
    "requirements": [],
    "default_lang": "en",
    "translations": {},
    "translation_index_usage": {},
    "preferences": {},
    "params": [],
    "tabs": [
        {
            "name": "tab",
            "title": "Tab",
            "preferences": {},
            "resources": []
        }
    ],
    "embedmacs": False,
    "embedded": [],
    "wiring": {
        "inputs": [],
        "outputs": [],
        "version": "2.0",
        "connections": [],
        "operators": {},
        "visualdescription": {
            "behaviours": [],
            "components": {
                "widget": {},
                "operator": {}
            },
            "connections": []
        }
    }
}
