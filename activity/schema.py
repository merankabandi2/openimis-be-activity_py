import graphene
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.apps import apps

from core.schema import OrderedDjangoFilterConnectionField

from activity.gql_queries import (
    PTBAGQLType, ComposanteGQLType, SousComposanteGQLType,
    ActiviteGQLType, SousActiviteGQLType,
    FundingSourceGQLType, SousActiviteFundingGQLType,
    QuarterlyExecutionGQLType, ActivityStatusTransitionGQLType,
    WeeklyPlanEntryGQLType,
)
from activity.gql_mutations import (
    CreatePTBAMutation, UpdatePTBAMutation, DeletePTBAMutation,
    ApprovePTBAMutation, ClosePTBAMutation,
    CreateComposanteMutation, UpdateComposanteMutation, DeleteComposanteMutation,
    CreateSousComposanteMutation, UpdateSousComposanteMutation, DeleteSousComposanteMutation,
    CreateActiviteMutation, UpdateActiviteMutation, DeleteActiviteMutation,
    CreateSousActiviteMutation, UpdateSousActiviteMutation, DeleteSousActiviteMutation,
    CreateFundingSourceMutation, UpdateFundingSourceMutation,
    AllocateFundingMutation,
    TransitionActivityMutation,
    ReportQuarterlyExecutionMutation,
    LinkActivityToIndicatorMutation,
    UnlinkActivityFromIndicatorMutation,
    CreateWeeklyPlanEntryMutation, UpdateWeeklyPlanEntryMutation,
    DeleteWeeklyPlanEntryMutation,
    AllocateFundingRevisedMutation,
    BeginRevisionMutation, ApproveRevisionMutation, RejectRevisionMutation,
)
from activity.dashboard_gql import PTBADashboardType
from activity.dashboard_service import PTBADashboardService


class Query(graphene.ObjectType):
    ptba = OrderedDjangoFilterConnectionField(
        PTBAGQLType,
        orderBy=graphene.List(of_type=graphene.String),
    )
    composante = OrderedDjangoFilterConnectionField(
        ComposanteGQLType,
        orderBy=graphene.List(of_type=graphene.String),
    )
    sous_composante = OrderedDjangoFilterConnectionField(
        SousComposanteGQLType,
        orderBy=graphene.List(of_type=graphene.String),
    )
    activite = OrderedDjangoFilterConnectionField(
        ActiviteGQLType,
        orderBy=graphene.List(of_type=graphene.String),
    )
    sous_activite = OrderedDjangoFilterConnectionField(
        SousActiviteGQLType,
        orderBy=graphene.List(of_type=graphene.String),
    )
    funding_source = OrderedDjangoFilterConnectionField(
        FundingSourceGQLType,
        orderBy=graphene.List(of_type=graphene.String),
    )
    sous_activite_funding = OrderedDjangoFilterConnectionField(
        SousActiviteFundingGQLType,
        orderBy=graphene.List(of_type=graphene.String),
    )
    quarterly_execution = OrderedDjangoFilterConnectionField(
        QuarterlyExecutionGQLType,
        orderBy=graphene.List(of_type=graphene.String),
    )
    activity_status_transition = OrderedDjangoFilterConnectionField(
        ActivityStatusTransitionGQLType,
        orderBy=graphene.List(of_type=graphene.String),
    )
    weekly_plan_entry = OrderedDjangoFilterConnectionField(
        WeeklyPlanEntryGQLType,
        orderBy=graphene.List(of_type=graphene.String),
    )

    ptba_dashboard = graphene.Field(
        PTBADashboardType,
        ptba_id=graphene.UUID(required=True),
        quarter=graphene.Int(),
        year=graphene.Int(),
    )

    def resolve_ptba_dashboard(self, info, ptba_id, quarter=None, year=None, **kwargs):
        user = info.context.user
        if type(user) is AnonymousUser or not user.id:
            raise ValidationError("mutation.authentication_required")
        config = apps.get_app_config('activity')
        if not user.has_perms(config.gql_dashboard_view_perms):
            raise ValidationError("mutation.authentication_required")
        data = PTBADashboardService.get_overview(ptba_id, quarter, year)
        return PTBADashboardType(**data)


class Mutation(graphene.ObjectType):
    create_ptba = CreatePTBAMutation.Field()
    update_ptba = UpdatePTBAMutation.Field()
    delete_ptba = DeletePTBAMutation.Field()

    create_composante = CreateComposanteMutation.Field()
    update_composante = UpdateComposanteMutation.Field()
    delete_composante = DeleteComposanteMutation.Field()

    create_sous_composante = CreateSousComposanteMutation.Field()
    update_sous_composante = UpdateSousComposanteMutation.Field()
    delete_sous_composante = DeleteSousComposanteMutation.Field()

    create_activite = CreateActiviteMutation.Field()
    update_activite = UpdateActiviteMutation.Field()
    delete_activite = DeleteActiviteMutation.Field()

    create_sous_activite = CreateSousActiviteMutation.Field()
    update_sous_activite = UpdateSousActiviteMutation.Field()
    delete_sous_activite = DeleteSousActiviteMutation.Field()

    create_funding_source = CreateFundingSourceMutation.Field()
    update_funding_source = UpdateFundingSourceMutation.Field()

    allocate_funding = AllocateFundingMutation.Field()
    transition_activity = TransitionActivityMutation.Field()
    report_quarterly_execution = ReportQuarterlyExecutionMutation.Field()

    link_activity_to_indicator = LinkActivityToIndicatorMutation.Field()
    unlink_activity_from_indicator = UnlinkActivityFromIndicatorMutation.Field()

    create_weekly_plan_entry = CreateWeeklyPlanEntryMutation.Field()
    update_weekly_plan_entry = UpdateWeeklyPlanEntryMutation.Field()
    delete_weekly_plan_entry = DeleteWeeklyPlanEntryMutation.Field()

    allocate_funding_revised = AllocateFundingRevisedMutation.Field()

    approve_ptba = ApprovePTBAMutation.Field()
    close_ptba = ClosePTBAMutation.Field()

    begin_revision = BeginRevisionMutation.Field()
    approve_revision = ApproveRevisionMutation.Field()
    reject_revision = RejectRevisionMutation.Field()
