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

# GET /preferences/platform/
get_platform_preference_collection_summary = "Get Platform Preferences"
get_platform_preference_collection_description = "Retrieve a list of preferences for the authenticated user"
get_platform_preference_collection_response_description = "List of platform preferences"
get_platform_preference_collection_not_found_response_description = "Platform preferences not found"
get_platform_preference_collection_response_example = {
    "preference-1": {
        "inherit": False,
        "value": "value-preference-1"
    },
    "language": {
        "inherit": False,
        "value": "es"
    }
}

# POST /preferences/platform/
create_platform_preference_collection_summary = "Update Platform Preferences"
create_platform_preference_collection_description = "Update the preferences for the authenticated user"
create_platform_preference_collection_response_description = "Platform preferences updated"
create_platform_preference_collection_platform_preference_create_description = "Platform preference data"
create_platform_preference_collection_auth_required_response_description = "Authentication required"
create_platform_preference_collection_validation_error_response_description = "Validation error"
create_platform_preference_collection_not_acceptable_response_description = "Invalid request content type"
create_platform_preference_collection_platform_preference_create_example = {
    "name": "lola-name",
    "preference-1": {
        "value": "3"
    }
}

# GET /workspace/{workspace_id}/preferences/
get_workspace_preference_collection_summary = "Get Workspace Preferences"
get_workspace_preference_collection_description = "Retrieve a list of preferences for the authenticated user in the workspace"
get_workspace_preference_collection_response_description = "List of workspace preferences"
get_workspace_preference_collection_auth_required_response_description = "Authentication required"
get_workspace_preference_collection_permission_denied_response_description = "Permission denied"
get_workspace_preference_collection_not_found_response_description = "Workspace not found"
get_workspace_preference_collection_workspace_id_description = "Workspace identifier"
get_workspace_preference_collection_response_example = {
    "preference-1": {
        "inherit": False,
        "value": "value-preference-1"
    },
    "preference-2": {
        "inherit": True,
        "value": 5
    },
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
}

# POST /workspace/{workspace_id}/preferences/
create_workspace_preference_collection_summary = "Update Workspace Preferences"
create_workspace_preference_collection_description = "Update the preferences for the authenticated user in the workspace"
create_workspace_preference_collection_response_description = "Workspace preferences updated"
create_workspace_preference_collection_platform_preference_create_description = "Workspace preference data"
create_workspace_preference_collection_auth_required_response_description = "Authentication required"
create_workspace_preference_collection_validation_error_response_description = "Validation error"
create_workspace_preference_collection_not_acceptable_response_description = "Invalid request content type"
create_workspace_preference_collection_permission_denied_response_description = "Permission denied"
create_workspace_preference_collection_workspace_id_description = "Workspace identifier"
create_workspace_preference_collection_platform_preference_create_example = {
    "name": "example",
    "preference-1": {
        "value": "value-preference-1"
    }
}

# GET /workspace/{workspace_id}/tab/{tab_id}/preferences/
get_tab_preference_collection_summary = "Get Tab Preferences"
get_tab_preference_collection_description = "Retrieve a list of preferences of the workspace tabs for the authenticated user"
get_tab_preference_collection_response_description = "List of tab preferences"
get_tab_preference_collection_auth_required_response_description = "Authentication required"
get_tab_preference_collection_permission_denied_response_description = "Permission denied"
get_tab_preference_collection_not_found_response_description = "Workspace or Tab not found"
get_tab_preference_collection_workspace_id_description = "Workspace identifier"
get_tab_preference_collection_tab_id_description = "Tab identifier"
get_tab_preference_collection_response_example = {
    "preference-1": {
        "inherit": False,
        "value": "value-preference-1"
    },
    "preference-2": {
        "inherit": False,
        "value": 5
    },
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
}

# POST /workspace/{workspace_id}/tab/{tab_id}/preferences/
create_tab_preference_collection_summary = "Update Tab Preferences"
create_tab_preference_collection_description = "Update the tab preferences for the authenticated user"
create_tab_preference_collection_response_description = "Tab preferences updated"
create_tab_preference_collection_platform_preference_create_description = "Tab Preference data"
create_tab_preference_collection_validation_error_response_description = "Validation error"
create_tab_preference_collection_not_acceptable_response_description = "Invalid request content type"
create_tab_preference_collection_permission_denied_response_description = "Permission denied"
create_tab_preference_collection_workspace_id_description = "Workspace identifier"
create_tab_preference_collection_tab_id_description = "Tab identifier"
create_tab_preference_collection_platform_preference_create_example = {
    "name": "example",
    "preference-1": {"value": "value-preference-1"}
}
