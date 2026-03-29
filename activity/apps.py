from django.apps import AppConfig

from .gql_config import (
    GQL_PTBA_SEARCH_PERMS, GQL_PTBA_CREATE_PERMS,
    GQL_PTBA_UPDATE_PERMS, GQL_PTBA_DELETE_PERMS,
    GQL_ACTIVITY_SEARCH_PERMS, GQL_ACTIVITY_CREATE_PERMS,
    GQL_ACTIVITY_UPDATE_PERMS, GQL_ACTIVITY_DELETE_PERMS,
    GQL_EXECUTION_REPORT_PERMS, GQL_EXECUTION_APPROVE_PERMS,
    GQL_TRANSITION_PERMS, GQL_DASHBOARD_VIEW_PERMS,
    GQL_FUNDING_MANAGE_PERMS,
)

MODULE_NAME = 'activity'

DEFAULT_CONFIG = {
    "gql_ptba_search_perms": GQL_PTBA_SEARCH_PERMS,
    "gql_ptba_create_perms": GQL_PTBA_CREATE_PERMS,
    "gql_ptba_update_perms": GQL_PTBA_UPDATE_PERMS,
    "gql_ptba_delete_perms": GQL_PTBA_DELETE_PERMS,
    "gql_activity_search_perms": GQL_ACTIVITY_SEARCH_PERMS,
    "gql_activity_create_perms": GQL_ACTIVITY_CREATE_PERMS,
    "gql_activity_update_perms": GQL_ACTIVITY_UPDATE_PERMS,
    "gql_activity_delete_perms": GQL_ACTIVITY_DELETE_PERMS,
    "gql_execution_report_perms": GQL_EXECUTION_REPORT_PERMS,
    "gql_execution_approve_perms": GQL_EXECUTION_APPROVE_PERMS,
    "gql_transition_perms": GQL_TRANSITION_PERMS,
    "gql_dashboard_view_perms": GQL_DASHBOARD_VIEW_PERMS,
    "gql_funding_manage_perms": GQL_FUNDING_MANAGE_PERMS,
}


class ActivityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = MODULE_NAME

    # PTBA permissions
    gql_ptba_search_perms = None
    gql_ptba_create_perms = None
    gql_ptba_update_perms = None
    gql_ptba_delete_perms = None

    # Activity permissions
    gql_activity_search_perms = None
    gql_activity_create_perms = None
    gql_activity_update_perms = None
    gql_activity_delete_perms = None

    # Execution permissions
    gql_execution_report_perms = None
    gql_execution_approve_perms = None

    # Lifecycle transition permission
    gql_transition_perms = None

    # Dashboard permission
    gql_dashboard_view_perms = None

    # Funding management permission
    gql_funding_manage_perms = None

    def ready(self):
        self.__load_config()
        # Import signals to register signal handlers
        import activity.signals  # noqa: F401

    def __load_config(self):
        """Load the module configuration including permissions"""
        cfg = DEFAULT_CONFIG

        self.gql_ptba_search_perms = cfg.get("gql_ptba_search_perms", GQL_PTBA_SEARCH_PERMS)
        self.gql_ptba_create_perms = cfg.get("gql_ptba_create_perms", GQL_PTBA_CREATE_PERMS)
        self.gql_ptba_update_perms = cfg.get("gql_ptba_update_perms", GQL_PTBA_UPDATE_PERMS)
        self.gql_ptba_delete_perms = cfg.get("gql_ptba_delete_perms", GQL_PTBA_DELETE_PERMS)

        self.gql_activity_search_perms = cfg.get("gql_activity_search_perms", GQL_ACTIVITY_SEARCH_PERMS)
        self.gql_activity_create_perms = cfg.get("gql_activity_create_perms", GQL_ACTIVITY_CREATE_PERMS)
        self.gql_activity_update_perms = cfg.get("gql_activity_update_perms", GQL_ACTIVITY_UPDATE_PERMS)
        self.gql_activity_delete_perms = cfg.get("gql_activity_delete_perms", GQL_ACTIVITY_DELETE_PERMS)

        self.gql_execution_report_perms = cfg.get("gql_execution_report_perms", GQL_EXECUTION_REPORT_PERMS)
        self.gql_execution_approve_perms = cfg.get("gql_execution_approve_perms", GQL_EXECUTION_APPROVE_PERMS)

        self.gql_transition_perms = cfg.get("gql_transition_perms", GQL_TRANSITION_PERMS)
        self.gql_dashboard_view_perms = cfg.get("gql_dashboard_view_perms", GQL_DASHBOARD_VIEW_PERMS)
        self.gql_funding_manage_perms = cfg.get("gql_funding_manage_perms", GQL_FUNDING_MANAGE_PERMS)
