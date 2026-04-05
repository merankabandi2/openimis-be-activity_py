import graphene
from gettext import gettext as _
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from django.apps import apps

from core.gql.gql_mutations.base_mutation import (
    BaseHistoryModelCreateMutationMixin, BaseMutation,
    BaseHistoryModelUpdateMutationMixin, BaseHistoryModelDeleteMutationMixin,
)
from core.schema import OpenIMISMutation
from activity.apps import ActivityConfig
from activity.models import (
    PTBA, PTBAStatus, Composante, SousComposante, Activite, SousActivite,
    FundingSource, SousActiviteFunding, WeeklyPlanEntry,
    ActivityStatusTransition, RevisionStatus,
)
from activity.services import ActivityLifecycleService, QuarterlyExecutionService


def get_activity_config():
    """Get the ActivityConfig instance"""
    return apps.get_app_config('activity')


# ---- PTBA mutations ----

class CreatePTBAInputType(OpenIMISMutation.Input):
    code = graphene.String(required=True)
    name = graphene.String(required=True)
    fiscal_year_start = graphene.Date(required=True)
    fiscal_year_end = graphene.Date(required=True)
    status = graphene.String(required=False)
    benefit_plan_id = graphene.UUID(required=False)
    json_ext = graphene.JSONString(required=False)


class UpdatePTBAInputType(CreatePTBAInputType):
    id = graphene.UUID(required=True)


class DeletePTBAInputType(OpenIMISMutation.Input):
    ids = graphene.List(graphene.UUID, required=True)


class CreatePTBAMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_class = "CreatePTBAMutation"
    _mutation_module = ActivityConfig.name
    _model = PTBA

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_ptba_create_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        PTBA.objects.create(
            code=data['code'],
            name=data['name'],
            fiscal_year_start=data['fiscal_year_start'],
            fiscal_year_end=data['fiscal_year_end'],
            status=data.get('status', 'DRAFT'),
            benefit_plan_id=data.get('benefit_plan_id'),
            json_ext=data.get('json_ext'),
            user_created=user,
            user_updated=user,
        )

    class Input(CreatePTBAInputType):
        pass


class UpdatePTBAMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "UpdatePTBAMutation"
    _mutation_module = ActivityConfig.name
    _model = PTBA

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_ptba_update_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        ptba = PTBA.objects.get(id=data['id'])
        update_data = {k: v for k, v in data.items() if k != 'id' and v is not None}
        update_data['user_updated'] = user
        ptba.update(data=update_data)

    class Input(UpdatePTBAInputType):
        pass


class DeletePTBAMutation(BaseHistoryModelDeleteMutationMixin, BaseMutation):
    _mutation_class = "DeletePTBAMutation"
    _mutation_module = ActivityConfig.name
    _model = PTBA

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_ptba_delete_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        ids = data.get('ids')
        if ids:
            with transaction.atomic():
                for ptba_id in ids:
                    PTBA.objects.filter(id=ptba_id).delete()

    class Input(DeletePTBAInputType):
        pass


# ---- Composante mutations ----

class CreateComposanteInputType(OpenIMISMutation.Input):
    ptba_id = graphene.UUID(required=True)
    code = graphene.String(required=True)
    name = graphene.String(required=True)
    sort_order = graphene.Int(required=False)


class UpdateComposanteInputType(CreateComposanteInputType):
    id = graphene.UUID(required=True)
    ptba_id = graphene.UUID(required=False)


class DeleteComposanteInputType(OpenIMISMutation.Input):
    ids = graphene.List(graphene.UUID, required=True)


class CreateComposanteMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_class = "CreateComposanteMutation"
    _mutation_module = ActivityConfig.name
    _model = Composante

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_ptba_create_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        Composante.objects.create(
            ptba_id=data['ptba_id'],
            code=data['code'],
            name=data['name'],
            sort_order=data.get('sort_order', 0),
        )

    class Input(CreateComposanteInputType):
        pass


class UpdateComposanteMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "UpdateComposanteMutation"
    _mutation_module = ActivityConfig.name
    _model = Composante

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_ptba_update_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        composante = Composante.objects.get(id=data['id'])
        update_data = {k: v for k, v in data.items() if k != 'id' and v is not None}
        composante.update(data=update_data)

    class Input(UpdateComposanteInputType):
        pass


class DeleteComposanteMutation(BaseHistoryModelDeleteMutationMixin, BaseMutation):
    _mutation_class = "DeleteComposanteMutation"
    _mutation_module = ActivityConfig.name
    _model = Composante

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_ptba_delete_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        ids = data.get('ids')
        if ids:
            with transaction.atomic():
                for item_id in ids:
                    Composante.objects.filter(id=item_id).delete()

    class Input(DeleteComposanteInputType):
        pass


# ---- SousComposante mutations ----

class CreateSousComposanteInputType(OpenIMISMutation.Input):
    composante_id = graphene.UUID(required=True)
    code = graphene.String(required=True)
    name = graphene.String(required=True)
    sort_order = graphene.Int(required=False)


class UpdateSousComposanteInputType(CreateSousComposanteInputType):
    id = graphene.UUID(required=True)
    composante_id = graphene.UUID(required=False)


class DeleteSousComposanteInputType(OpenIMISMutation.Input):
    ids = graphene.List(graphene.UUID, required=True)


class CreateSousComposanteMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_class = "CreateSousComposanteMutation"
    _mutation_module = ActivityConfig.name
    _model = SousComposante

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_ptba_create_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        SousComposante.objects.create(
            composante_id=data['composante_id'],
            code=data['code'],
            name=data['name'],
            sort_order=data.get('sort_order', 0),
        )

    class Input(CreateSousComposanteInputType):
        pass


class UpdateSousComposanteMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "UpdateSousComposanteMutation"
    _mutation_module = ActivityConfig.name
    _model = SousComposante

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_ptba_update_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        sc = SousComposante.objects.get(id=data['id'])
        update_data = {k: v for k, v in data.items() if k != 'id' and v is not None}
        sc.update(data=update_data)

    class Input(UpdateSousComposanteInputType):
        pass


class DeleteSousComposanteMutation(BaseHistoryModelDeleteMutationMixin, BaseMutation):
    _mutation_class = "DeleteSousComposanteMutation"
    _mutation_module = ActivityConfig.name
    _model = SousComposante

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_ptba_delete_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        ids = data.get('ids')
        if ids:
            with transaction.atomic():
                for item_id in ids:
                    SousComposante.objects.filter(id=item_id).delete()

    class Input(DeleteSousComposanteInputType):
        pass


# ---- Activite mutations ----

class CreateActiviteInputType(OpenIMISMutation.Input):
    sous_composante_id = graphene.UUID(required=True)
    code = graphene.String(required=False)
    name = graphene.String(required=True)
    indicator_description = graphene.String(required=False)
    province = graphene.String(required=False)
    location_id = graphene.Int(required=False)
    implementing_structure = graphene.String(required=False)
    procurement_method = graphene.String(required=False)
    observations = graphene.String(required=False)
    sort_order = graphene.Int(required=False)
    json_ext = graphene.JSONString(required=False)
    revision_status = graphene.String(required=False)
    revision_comment = graphene.String(required=False)


class UpdateActiviteInputType(CreateActiviteInputType):
    id = graphene.UUID(required=True)
    sous_composante_id = graphene.UUID(required=False)


class DeleteActiviteInputType(OpenIMISMutation.Input):
    ids = graphene.List(graphene.UUID, required=True)


class CreateActiviteMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_class = "CreateActiviteMutation"
    _mutation_module = ActivityConfig.name
    _model = Activite

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_activity_create_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        Activite.objects.create(
            sous_composante_id=data['sous_composante_id'],
            code=data.get('code', ''),
            name=data['name'],
            indicator_description=data.get('indicator_description', ''),
            province=data.get('province', ''),
            location_id=data.get('location_id'),
            implementing_structure=data.get('implementing_structure', ''),
            procurement_method=data.get('procurement_method', ''),
            observations=data.get('observations', ''),
            sort_order=data.get('sort_order', 0),
            json_ext=data.get('json_ext'),
            revision_status=data.get('revision_status', 'INITIAL'),
            revision_comment=data.get('revision_comment', ''),
        )

    class Input(CreateActiviteInputType):
        pass


class UpdateActiviteMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "UpdateActiviteMutation"
    _mutation_module = ActivityConfig.name
    _model = Activite

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_activity_update_perms):
            raise ValidationError(_("mutation.authentication_required"))

    CLEARABLE_FIELDS = {
        'revision_comment',
    }

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        activite = Activite.objects.get(id=data['id'])
        update_data = {
            k: v for k, v in data.items()
            if k != 'id' and (v is not None or k in cls.CLEARABLE_FIELDS)
        }
        activite.update(data=update_data)

    class Input(UpdateActiviteInputType):
        pass


class DeleteActiviteMutation(BaseHistoryModelDeleteMutationMixin, BaseMutation):
    _mutation_class = "DeleteActiviteMutation"
    _mutation_module = ActivityConfig.name
    _model = Activite

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_activity_delete_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        ids = data.get('ids')
        if ids:
            with transaction.atomic():
                for item_id in ids:
                    Activite.objects.filter(id=item_id).delete()

    class Input(DeleteActiviteInputType):
        pass


# ---- SousActivite mutations ----

class CreateSousActiviteInputType(OpenIMISMutation.Input):
    activite_id = graphene.UUID(required=True)
    code = graphene.String(required=False)
    name = graphene.String(required=True)
    expense_category_code = graphene.String(required=False)
    expense_category = graphene.String(required=False)
    unit = graphene.String(required=False)
    quantity_total = graphene.Decimal(required=False)
    quantity_t1 = graphene.Decimal(required=False)
    quantity_t2 = graphene.Decimal(required=False)
    quantity_t3 = graphene.Decimal(required=False)
    quantity_t4 = graphene.Decimal(required=False)
    unit_cost = graphene.Decimal(required=False)
    budget_t1 = graphene.Decimal(required=False)
    budget_t2 = graphene.Decimal(required=False)
    budget_t3 = graphene.Decimal(required=False)
    budget_t4 = graphene.Decimal(required=False)
    budget_total = graphene.Decimal(required=False)
    sort_order = graphene.Int(required=False)
    json_ext = graphene.JSONString(required=False)
    # Revision tracking
    quantity_initial = graphene.Decimal(required=False)
    quantity_revised = graphene.Decimal(required=False)
    unit_cost_initial = graphene.Decimal(required=False)
    unit_cost_revised = graphene.Decimal(required=False)
    budget_initial = graphene.Decimal(required=False)
    budget_revised = graphene.Decimal(required=False)
    # Scheduling
    date_start = graphene.Date(required=False)
    date_end = graphene.Date(required=False)
    # Responsibility
    responsible = graphene.String(required=False)
    intervenants = graphene.String(required=False)
    # Revision status
    revision_status = graphene.String(required=False)
    revision_comment = graphene.String(required=False)


class UpdateSousActiviteInputType(CreateSousActiviteInputType):
    id = graphene.UUID(required=True)
    activite_id = graphene.UUID(required=False)


class DeleteSousActiviteInputType(OpenIMISMutation.Input):
    ids = graphene.List(graphene.UUID, required=True)


class CreateSousActiviteMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_class = "CreateSousActiviteMutation"
    _mutation_module = ActivityConfig.name
    _model = SousActivite

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_activity_create_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        SousActivite.objects.create(
            activite_id=data['activite_id'],
            code=data.get('code', ''),
            name=data['name'],
            expense_category_code=data.get('expense_category_code', ''),
            expense_category=data.get('expense_category', ''),
            unit=data.get('unit', ''),
            quantity_total=data.get('quantity_total', 0),
            quantity_t1=data.get('quantity_t1', 0),
            quantity_t2=data.get('quantity_t2', 0),
            quantity_t3=data.get('quantity_t3', 0),
            quantity_t4=data.get('quantity_t4', 0),
            unit_cost=data.get('unit_cost', 0),
            budget_t1=data.get('budget_t1', 0),
            budget_t2=data.get('budget_t2', 0),
            budget_t3=data.get('budget_t3', 0),
            budget_t4=data.get('budget_t4', 0),
            budget_total=data.get('budget_total', 0),
            sort_order=data.get('sort_order', 0),
            json_ext=data.get('json_ext'),
            quantity_initial=data.get('quantity_initial', 0),
            quantity_revised=data.get('quantity_revised'),
            unit_cost_initial=data.get('unit_cost_initial', 0),
            unit_cost_revised=data.get('unit_cost_revised'),
            budget_initial=data.get('budget_initial', 0),
            budget_revised=data.get('budget_revised'),
            date_start=data.get('date_start'),
            date_end=data.get('date_end'),
            responsible=data.get('responsible', ''),
            intervenants=data.get('intervenants', ''),
            revision_status=data.get('revision_status', 'INITIAL'),
            revision_comment=data.get('revision_comment', ''),
        )

    class Input(CreateSousActiviteInputType):
        pass


class UpdateSousActiviteMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "UpdateSousActiviteMutation"
    _mutation_module = ActivityConfig.name
    _model = SousActivite

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_activity_update_perms):
            raise ValidationError(_("mutation.authentication_required"))

    # Fields that may be explicitly set to None (cleared) via the API
    CLEARABLE_FIELDS = {
        'quantity_revised', 'unit_cost_revised', 'budget_revised',
        'revision_comment', 'date_start', 'date_end',
    }

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        sa = SousActivite.objects.get(id=data['id'])
        update_data = {
            k: v for k, v in data.items()
            if k != 'id' and (v is not None or k in cls.CLEARABLE_FIELDS)
        }
        sa.update(data=update_data)

    class Input(UpdateSousActiviteInputType):
        pass


class DeleteSousActiviteMutation(BaseHistoryModelDeleteMutationMixin, BaseMutation):
    _mutation_class = "DeleteSousActiviteMutation"
    _mutation_module = ActivityConfig.name
    _model = SousActivite

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_activity_delete_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        ids = data.get('ids')
        if ids:
            with transaction.atomic():
                for item_id in ids:
                    SousActivite.objects.filter(id=item_id).delete()

    class Input(DeleteSousActiviteInputType):
        pass


# ---- FundingSource mutations ----

class CreateFundingSourceInputType(OpenIMISMutation.Input):
    code = graphene.String(required=True)
    name = graphene.String(required=True)
    is_active = graphene.Boolean(required=False)


class UpdateFundingSourceInputType(CreateFundingSourceInputType):
    id = graphene.UUID(required=True)


class CreateFundingSourceMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_class = "CreateFundingSourceMutation"
    _mutation_module = ActivityConfig.name
    _model = FundingSource

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_funding_manage_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        FundingSource.objects.create(
            code=data['code'],
            name=data['name'],
            is_active=data.get('is_active', True),
        )

    class Input(CreateFundingSourceInputType):
        pass


class UpdateFundingSourceMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "UpdateFundingSourceMutation"
    _mutation_module = ActivityConfig.name
    _model = FundingSource

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_funding_manage_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        fs = FundingSource.objects.get(id=data['id'])
        update_data = {k: v for k, v in data.items() if k != 'id' and v is not None}
        fs.update(data=update_data)

    class Input(UpdateFundingSourceInputType):
        pass


# ---- Allocate Funding mutation ----

class AllocateFundingInputType(OpenIMISMutation.Input):
    sous_activite_id = graphene.UUID(required=True)
    funding_source_id = graphene.UUID(required=True)
    amount = graphene.Decimal(required=True)


class AllocateFundingMutation(BaseMutation):
    _mutation_class = "AllocateFundingMutation"
    _mutation_module = ActivityConfig.name

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_funding_manage_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        SousActiviteFunding.objects.update_or_create(
            sous_activite_id=data['sous_activite_id'],
            funding_source_id=data['funding_source_id'],
            defaults={'amount': data['amount']},
        )

    class Input(AllocateFundingInputType):
        pass


# ---- Transition Activity mutation ----

class TransitionActivityInputType(OpenIMISMutation.Input):
    activite_id = graphene.UUID(required=True)
    to_status = graphene.String(required=True)
    comment = graphene.String(required=False)


class TransitionActivityMutation(BaseMutation):
    _mutation_class = "TransitionActivityMutation"
    _mutation_module = ActivityConfig.name

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id:
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        activite = Activite.objects.get(id=data['activite_id'])
        to_status = data['to_status']
        ActivityLifecycleService.transition(
            activite,
            to_status,
            user,
            data.get('comment', ''),
        )

        # Send notification on status transition
        try:
            from notification.services import NotificationService
            event_map = {
                'EN_COURS': 'activity.submitted',
                'REALISE': 'activity.validated',
            }
            event_code = event_map.get(to_status)
            if event_code:
                NotificationService.notify(
                    event_code=event_code,
                    actor=user,
                    entity=activite,
                    entity_url=f'/activity/activite/{activite.id}',
                    recipients=[],
                    context={
                        'activity_type': activite.name,
                        'new_status': to_status,
                    },
                )
        except Exception as e:
            import logging
            logging.getLogger('openIMIS').warning(f"Notification failed: {e}")

    class Input(TransitionActivityInputType):
        pass


# ---- Report Quarterly Execution mutation ----

class ReportQuarterlyExecutionInputType(OpenIMISMutation.Input):
    sous_activite_id = graphene.UUID(required=True)
    quarter = graphene.Int(required=True)
    year = graphene.Int(required=True)
    budget_engage = graphene.Decimal(required=False)
    budget_decaisse = graphene.Decimal(required=False)
    resultats_realises = graphene.Decimal(required=False)
    observations = graphene.String(required=False)


class ReportQuarterlyExecutionMutation(BaseMutation):
    _mutation_class = "ReportQuarterlyExecutionMutation"
    _mutation_module = ActivityConfig.name

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_execution_report_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        sa = SousActivite.objects.get(id=data['sous_activite_id'])
        QuarterlyExecutionService.report(
            sous_activite=sa,
            quarter=data['quarter'],
            year=data['year'],
            user=user,
            budget_engage=data.get('budget_engage'),
            budget_decaisse=data.get('budget_decaisse'),
            resultats_realises=data.get('resultats_realises'),
            observations=data.get('observations', ''),
        )

    class Input(ReportQuarterlyExecutionInputType):
        pass


# ---- Link/Unlink Activity to M&E Indicator mutations ----

class LinkActivityToIndicatorInputType(OpenIMISMutation.Input):
    activite_id = graphene.UUID(required=True)
    indicator_id = graphene.Int(required=True)


class LinkActivityToIndicatorMutation(BaseMutation):
    _mutation_class = "LinkActivityToIndicatorMutation"
    _mutation_module = ActivityConfig.name

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_activity_update_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        activite = Activite.objects.get(id=data['activite_id'])
        if not hasattr(activite, 'indicators'):
            raise ValidationError(
                _("merankabandi module not installed; cannot link indicators")
            )
        try:
            from merankabandi.models import Indicator
        except ImportError:
            raise ValidationError(
                _("merankabandi module not installed; cannot link indicators")
            )
        indicator = Indicator.objects.get(id=data['indicator_id'])
        activite.indicators.add(indicator)

    class Input(LinkActivityToIndicatorInputType):
        pass


class UnlinkActivityFromIndicatorInputType(OpenIMISMutation.Input):
    activite_id = graphene.UUID(required=True)
    indicator_id = graphene.Int(required=True)


class UnlinkActivityFromIndicatorMutation(BaseMutation):
    _mutation_class = "UnlinkActivityFromIndicatorMutation"
    _mutation_module = ActivityConfig.name

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_activity_update_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        activite = Activite.objects.get(id=data['activite_id'])
        if not hasattr(activite, 'indicators'):
            raise ValidationError(
                _("merankabandi module not installed; cannot unlink indicators")
            )
        try:
            from merankabandi.models import Indicator
        except ImportError:
            raise ValidationError(
                _("merankabandi module not installed; cannot unlink indicators")
            )
        indicator = Indicator.objects.get(id=data['indicator_id'])
        activite.indicators.remove(indicator)

    class Input(UnlinkActivityFromIndicatorInputType):
        pass


# ---- WeeklyPlanEntry mutations ----

class CreateWeeklyPlanEntryInputType(OpenIMISMutation.Input):
    sous_activite_id = graphene.UUID(required=True)
    week_start = graphene.Date(required=True)
    week_end = graphene.Date(required=True)
    planned_description = graphene.String(required=False)
    status_description = graphene.String(required=False)
    status = graphene.String(required=False)
    responsible = graphene.String(required=False)
    intervenants = graphene.String(required=False)


class UpdateWeeklyPlanEntryInputType(CreateWeeklyPlanEntryInputType):
    id = graphene.UUID(required=True)
    sous_activite_id = graphene.UUID(required=False)
    week_start = graphene.Date(required=False)
    week_end = graphene.Date(required=False)


class DeleteWeeklyPlanEntryInputType(OpenIMISMutation.Input):
    ids = graphene.List(graphene.UUID, required=True)


class CreateWeeklyPlanEntryMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_class = "CreateWeeklyPlanEntryMutation"
    _mutation_module = ActivityConfig.name
    _model = WeeklyPlanEntry

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_activity_create_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        WeeklyPlanEntry.objects.create(
            sous_activite_id=data['sous_activite_id'],
            week_start=data['week_start'],
            week_end=data['week_end'],
            planned_description=data.get('planned_description', ''),
            status_description=data.get('status_description', ''),
            status=data.get('status', 'PLANIFIE'),
            responsible=data.get('responsible', ''),
            intervenants=data.get('intervenants', ''),
            created_by=user,
        )

    class Input(CreateWeeklyPlanEntryInputType):
        pass


class UpdateWeeklyPlanEntryMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = "UpdateWeeklyPlanEntryMutation"
    _mutation_module = ActivityConfig.name
    _model = WeeklyPlanEntry

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_activity_update_perms):
            raise ValidationError(_("mutation.authentication_required"))

    CLEARABLE_FIELDS = {
        'planned_description', 'status_description',
        'responsible', 'intervenants',
    }

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        entry = WeeklyPlanEntry.objects.get(id=data['id'])
        update_data = {
            k: v for k, v in data.items()
            if k != 'id' and (v is not None or k in cls.CLEARABLE_FIELDS)
        }
        entry.update(data=update_data)

    class Input(UpdateWeeklyPlanEntryInputType):
        pass


class DeleteWeeklyPlanEntryMutation(BaseHistoryModelDeleteMutationMixin, BaseMutation):
    _mutation_class = "DeleteWeeklyPlanEntryMutation"
    _mutation_module = ActivityConfig.name
    _model = WeeklyPlanEntry

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_activity_delete_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        ids = data.get('ids')
        if ids:
            with transaction.atomic():
                for item_id in ids:
                    WeeklyPlanEntry.objects.filter(id=item_id).delete()

    class Input(DeleteWeeklyPlanEntryInputType):
        pass


# ---- AllocateFunding with initial/revised ----

class AllocateFundingRevisedInputType(OpenIMISMutation.Input):
    sous_activite_id = graphene.UUID(required=True)
    funding_source_id = graphene.UUID(required=True)
    amount = graphene.Decimal(required=True)
    amount_initial = graphene.Decimal(required=False)
    amount_revised = graphene.Decimal(required=False)


class AllocateFundingRevisedMutation(BaseMutation):
    _mutation_class = "AllocateFundingRevisedMutation"
    _mutation_module = ActivityConfig.name

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_funding_manage_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        defaults = {'amount': data['amount']}
        if data.get('amount_initial') is not None:
            defaults['amount_initial'] = data['amount_initial']
        if data.get('amount_revised') is not None:
            defaults['amount_revised'] = data['amount_revised']
        SousActiviteFunding.objects.update_or_create(
            sous_activite_id=data['sous_activite_id'],
            funding_source_id=data['funding_source_id'],
            defaults=defaults,
        )

    class Input(AllocateFundingRevisedInputType):
        pass


# ---- Approve / Close PTBA mutations ----

class ApprovePTBAInputType(OpenIMISMutation.Input):
    ptba_id = graphene.UUID(required=True)
    comment = graphene.String(required=False)


class ApprovePTBAMutation(BaseMutation):
    """Transition PTBA from DRAFT to APPROVED."""
    _mutation_class = "ApprovePTBAMutation"
    _mutation_module = ActivityConfig.name

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_ptba_update_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        ptba = PTBA.objects.get(id=data['ptba_id'])
        if ptba.status != PTBAStatus.DRAFT:
            raise ValidationError(
                _("PTBA must be in DRAFT status to approve. Current status: %(status)s")
                % {'status': ptba.status}
            )
        ptba.status = PTBAStatus.APPROVED
        ptba.user_updated = user
        ptba.save()

    class Input(ApprovePTBAInputType):
        pass


class ClosePTBAInputType(OpenIMISMutation.Input):
    ptba_id = graphene.UUID(required=True)
    comment = graphene.String(required=False)


class ClosePTBAMutation(BaseMutation):
    """Transition PTBA from ACTIVE to CLOSED."""
    _mutation_class = "ClosePTBAMutation"
    _mutation_module = ActivityConfig.name

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_ptba_update_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        ptba = PTBA.objects.get(id=data['ptba_id'])
        if ptba.status != PTBAStatus.ACTIVE:
            raise ValidationError(
                _("PTBA must be in ACTIVE status to close. Current status: %(status)s")
                % {'status': ptba.status}
            )
        ptba.status = PTBAStatus.CLOSED
        ptba.user_updated = user
        ptba.save()

    class Input(ClosePTBAInputType):
        pass


# ---- Revision workflow mutations for SousActivite ----

class BeginRevisionInputType(OpenIMISMutation.Input):
    sous_activite_id = graphene.UUID(required=True)


class BeginRevisionMutation(BaseMutation):
    """Begin a revision: snapshot current values into *_initial fields."""
    _mutation_class = "BeginRevisionMutation"
    _mutation_module = ActivityConfig.name

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_activity_update_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        sa = SousActivite.objects.get(id=data['sous_activite_id'])
        sa.quantity_initial = sa.quantity_total
        sa.unit_cost_initial = sa.unit_cost
        sa.budget_initial = sa.budget_total
        sa.revision_status = 'REVISE'
        sa.save()

    class Input(BeginRevisionInputType):
        pass


class ApproveRevisionInputType(OpenIMISMutation.Input):
    sous_activite_id = graphene.UUID(required=True)
    comment = graphene.String(required=False)


class ApproveRevisionMutation(BaseMutation):
    """Approve a revision: copy current values to *_revised fields."""
    _mutation_class = "ApproveRevisionMutation"
    _mutation_module = ActivityConfig.name

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_execution_approve_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        sa = SousActivite.objects.get(id=data['sous_activite_id'])
        if sa.revision_status != 'REVISE':
            raise ValidationError(
                _("SousActivite must be in REVISE status to approve revision. "
                  "Current: %(status)s") % {'status': sa.revision_status}
            )
        sa.quantity_revised = sa.quantity_total
        sa.unit_cost_revised = sa.unit_cost
        sa.budget_revised = sa.budget_total
        sa.revision_status = 'INITIAL'
        sa.revision_comment = data.get('comment', '')
        sa.save()

    class Input(ApproveRevisionInputType):
        pass


class RejectRevisionInputType(OpenIMISMutation.Input):
    sous_activite_id = graphene.UUID(required=True)
    reason = graphene.String(required=False)


class RejectRevisionMutation(BaseMutation):
    """Reject a revision: restore *_initial values back to current."""
    _mutation_class = "RejectRevisionMutation"
    _mutation_module = ActivityConfig.name

    @classmethod
    def _validate_mutation(cls, user, **data):
        if type(user) is AnonymousUser or not user.id or not user.has_perms(
                get_activity_config().gql_execution_approve_perms):
            raise ValidationError(_("mutation.authentication_required"))

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        sa = SousActivite.objects.get(id=data['sous_activite_id'])
        if sa.revision_status != 'REVISE':
            raise ValidationError(
                _("SousActivite must be in REVISE status to reject revision. "
                  "Current: %(status)s") % {'status': sa.revision_status}
            )
        sa.quantity_total = sa.quantity_initial
        sa.unit_cost = sa.unit_cost_initial
        sa.budget_total = sa.budget_initial
        sa.revision_status = 'ABANDONNE'
        sa.revision_comment = data.get('reason', '')
        sa.save()

    class Input(RejectRevisionInputType):
        pass
