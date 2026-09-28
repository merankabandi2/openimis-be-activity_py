"""
GraphQL Permission Configuration for Activity Module

This module defines all the permissions used by the Activity module.
Permission range: 802005-802017. 170001-170004 belong to social_protection
(gql_beneficiary_*_perms) and are not used here.
"""

# PTBA Management Permissions (802014-802017)
GQL_PTBA_SEARCH_PERMS = ["802014"]
GQL_PTBA_CREATE_PERMS = ["802015"]
GQL_PTBA_UPDATE_PERMS = ["802016"]
GQL_PTBA_DELETE_PERMS = ["802017"]

# Activity Management Permissions (802005-802008)
GQL_ACTIVITY_SEARCH_PERMS = ["802005"]
GQL_ACTIVITY_CREATE_PERMS = ["802006"]
GQL_ACTIVITY_UPDATE_PERMS = ["802007"]
GQL_ACTIVITY_DELETE_PERMS = ["802008"]

# Execution Permissions (802009-802010)
GQL_EXECUTION_REPORT_PERMS = ["802009"]
GQL_EXECUTION_APPROVE_PERMS = ["802010"]

# Lifecycle Transition Permission (802011)
GQL_TRANSITION_PERMS = ["802011"]

# Dashboard Permission (802012)
GQL_DASHBOARD_VIEW_PERMS = ["802012"]

# Funding Management Permission (802013)
GQL_FUNDING_MANAGE_PERMS = ["802013"]

# Permission Descriptions for Documentation
PERMISSION_DESCRIPTIONS = {
    "802005": "Search and view activities",
    "802006": "Create new activities",
    "802007": "Update existing activities",
    "802008": "Delete activities",
    "802009": "Report quarterly execution",
    "802010": "Approve quarterly execution",
    "802011": "Transition activity status",
    "802012": "View activity dashboards",
    "802013": "Manage funding sources and allocations",
    "802014": "Search and view PTBAs",
    "802015": "Create new PTBAs",
    "802016": "Update existing PTBAs",
    "802017": "Delete PTBAs",
}
