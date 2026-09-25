"""
GraphQL Permission Configuration for Activity Module

This module defines all the permissions used by the Activity module.
Permission range: 170005-170017. 170001-170004 belong to social_protection
(gql_beneficiary_*_perms) and are not used here.
"""

# PTBA Management Permissions (170014-170017)
GQL_PTBA_SEARCH_PERMS = ["170014"]
GQL_PTBA_CREATE_PERMS = ["170015"]
GQL_PTBA_UPDATE_PERMS = ["170016"]
GQL_PTBA_DELETE_PERMS = ["170017"]

# Activity Management Permissions (170005-170008)
GQL_ACTIVITY_SEARCH_PERMS = ["170005"]
GQL_ACTIVITY_CREATE_PERMS = ["170006"]
GQL_ACTIVITY_UPDATE_PERMS = ["170007"]
GQL_ACTIVITY_DELETE_PERMS = ["170008"]

# Execution Permissions (170009-170010)
GQL_EXECUTION_REPORT_PERMS = ["170009"]
GQL_EXECUTION_APPROVE_PERMS = ["170010"]

# Lifecycle Transition Permission (170011)
GQL_TRANSITION_PERMS = ["170011"]

# Dashboard Permission (170012)
GQL_DASHBOARD_VIEW_PERMS = ["170012"]

# Funding Management Permission (170013)
GQL_FUNDING_MANAGE_PERMS = ["170013"]

# Permission Descriptions for Documentation
PERMISSION_DESCRIPTIONS = {
    "170005": "Search and view activities",
    "170006": "Create new activities",
    "170007": "Update existing activities",
    "170008": "Delete activities",
    "170009": "Report quarterly execution",
    "170010": "Approve quarterly execution",
    "170011": "Transition activity status",
    "170012": "View activity dashboards",
    "170013": "Manage funding sources and allocations",
    "170014": "Search and view PTBAs",
    "170015": "Create new PTBAs",
    "170016": "Update existing PTBAs",
    "170017": "Delete PTBAs",
}
