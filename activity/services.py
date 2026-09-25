import logging
from django.utils import timezone

from activity.models import (
    ActivityStatus, ActivityStatusTransition, QuarterlyExecution,
)

logger = logging.getLogger(__name__)


class ActivityLifecycleService:
    """Service for managing activity status transitions."""

    VALID_TRANSITIONS = {
        ActivityStatus.PLANIFIE: [ActivityStatus.BUDGETISE],
        ActivityStatus.BUDGETISE: [ActivityStatus.EN_COURS, ActivityStatus.PLANIFIE],
        ActivityStatus.EN_COURS: [ActivityStatus.REALISE],
        ActivityStatus.REALISE: [ActivityStatus.CLOTURE, ActivityStatus.EN_COURS],
        ActivityStatus.CLOTURE: [],
    }

    # Name of the activity app-config right list each transition requires.
    TRANSITION_PERMS = {
        (ActivityStatus.PLANIFIE, ActivityStatus.BUDGETISE): 'gql_ptba_update_perms',
        (ActivityStatus.BUDGETISE, ActivityStatus.EN_COURS): 'gql_transition_perms',
        (ActivityStatus.EN_COURS, ActivityStatus.REALISE): 'gql_execution_report_perms',
        (ActivityStatus.REALISE, ActivityStatus.CLOTURE): 'gql_execution_approve_perms',
        (ActivityStatus.BUDGETISE, ActivityStatus.PLANIFIE): 'gql_transition_perms',
        (ActivityStatus.REALISE, ActivityStatus.EN_COURS): 'gql_transition_perms',
    }

    @classmethod
    def required_perms(cls, from_status, to_status):
        from django.apps import apps
        config_name = cls.TRANSITION_PERMS.get((from_status, to_status))
        if not config_name:
            return []
        return getattr(apps.get_app_config('activity'), config_name)

    @classmethod
    def transition(cls, activite, to_status, user, comment=''):
        from_status = activite.status

        valid_targets = cls.VALID_TRANSITIONS.get(from_status, [])
        if to_status not in valid_targets:
            raise ValueError(
                f"Cannot transition from {from_status} to {to_status}. "
                f"Valid targets: {valid_targets}"
            )

        required_perms = cls.required_perms(from_status, to_status)
        if required_perms and not user.has_perms(required_perms):
            raise PermissionError(
                f"Insufficient permissions for transition {from_status} -> {to_status}"
            )

        # Validate preconditions
        from activity.validation import validate_transition_preconditions
        errors = validate_transition_preconditions(activite, to_status)
        if errors:
            raise ValueError('; '.join(errors))

        activite.status = to_status
        if to_status == ActivityStatus.EN_COURS:
            activite.approved_by = user
            activite.approved_date = timezone.now()
        elif to_status == ActivityStatus.CLOTURE:
            activite.closed_by = user
            activite.closed_date = timezone.now()
        activite.save()

        ActivityStatusTransition.objects.create(
            activite=activite,
            from_status=from_status,
            to_status=to_status,
            transitioned_by=user,
            comment=comment,
        )

        logger.info(
            "Activity %s transitioned from %s to %s by user %s",
            activite.code, from_status, to_status, user,
        )
        return activite


class QuarterlyExecutionService:
    """Service for recording quarterly execution data."""

    @classmethod
    def report(cls, sous_activite, quarter, year, user, **data):
        if sous_activite.activite.status != ActivityStatus.EN_COURS:
            raise ValueError(
                "Activity must be EN_COURS to report execution. "
                f"Current status: {sous_activite.activite.status}"
            )

        from decimal import Decimal
        budget_prevu = getattr(sous_activite, f"budget_t{quarter}", Decimal('0')) or Decimal('0')
        resultats_attendus = getattr(sous_activite, f"quantity_t{quarter}", Decimal('0')) or Decimal('0')

        budget_engage = Decimal(str(data.get('budget_engage', 0) or 0))
        budget_decaisse = Decimal(str(data.get('budget_decaisse', 0) or 0))
        resultats_realises = Decimal(str(data.get('resultats_realises', 0) or 0))
        observations = data.get('observations', '')

        taux_engagement = Decimal('0')
        taux_decaissement = Decimal('0')
        taux_realisation = Decimal('0')

        if budget_prevu:
            taux_engagement = (budget_engage / budget_prevu) * 100
            taux_decaissement = (budget_decaisse / budget_prevu) * 100
        if resultats_attendus:
            taux_realisation = (resultats_realises / resultats_attendus) * 100

        execution, created = QuarterlyExecution.objects.update_or_create(
            sous_activite=sous_activite,
            quarter=quarter,
            year=year,
            defaults={
                'budget_prevu': budget_prevu,
                'budget_engage': budget_engage,
                'budget_decaisse': budget_decaisse,
                'resultats_attendus': resultats_attendus,
                'resultats_realises': resultats_realises,
                'taux_engagement': taux_engagement,
                'taux_decaissement': taux_decaissement,
                'taux_realisation': taux_realisation,
                'observations': observations,
                'reported_by': user,
                'reported_date': timezone.now(),
            },
        )

        logger.info(
            "Quarterly execution reported for %s T%s %s (created=%s)",
            sous_activite.code, quarter, year, created,
        )
        return execution
