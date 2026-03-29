"""Tests for ActivityLifecycleService transitions and validation."""
import uuid
from django.test import TestCase
from core.test_helpers import LogInHelper
from activity.models import (
    PTBA, Composante, SousComposante, Activite, SousActivite,
    ActivityStatus, ActivityStatusTransition,
)
from activity.services import ActivityLifecycleService


class LifecycleTransitionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from core.test_helpers import create_test_role
        role = create_test_role(
            perm_names=[
                'gql_ptba_update_perms',
                'gql_execution_report_perms',
                'gql_execution_approve_perms',
                'gql_transition_perms',
            ],
            name="ActivityLifecycleTestRole",
        )
        cls.user = LogInHelper().get_or_create_user_api(
            username='lifecycle_test', roles=[role.id],
        )
        cls.ptba = PTBA.objects.create(
            code='PTBA-LC', name='Lifecycle Test',
            fiscal_year_start='2025-01-01', fiscal_year_end='2025-12-31',
            user_created=cls.user, user_updated=cls.user,
        )
        cls.comp = Composante.objects.create(ptba=cls.ptba, code='1', name='Test Comp')
        cls.sc = SousComposante.objects.create(composante=cls.comp, code='1.1', name='Test SC')

    def _create_activity(self, status=ActivityStatus.PLANIFIE):
        act = Activite.objects.create(
            sous_composante=self.sc, code=f'A-{uuid.uuid4().hex[:6]}',
            name='Test Activity', status=status,
        )
        # Add a sous-activite with budget for BUDGETISE transition
        SousActivite.objects.create(
            activite=act, name='SA1', unit='unit',
            budget_total=1000, budget_t1=1000, unit_cost=100, quantity_total=10,
        )
        return act

    def test_valid_transition_planifie_to_budgetise(self):
        act = self._create_activity(ActivityStatus.PLANIFIE)
        ActivityLifecycleService.transition(act, ActivityStatus.BUDGETISE, self.user)
        act.refresh_from_db()
        self.assertEqual(act.status, ActivityStatus.BUDGETISE)

    def test_valid_transition_budgetise_to_en_cours(self):
        act = self._create_activity(ActivityStatus.BUDGETISE)
        ActivityLifecycleService.transition(act, ActivityStatus.EN_COURS, self.user)
        act.refresh_from_db()
        self.assertEqual(act.status, ActivityStatus.EN_COURS)
        self.assertIsNotNone(act.approved_by)
        self.assertIsNotNone(act.approved_date)

    def test_valid_transition_en_cours_to_realise(self):
        act = self._create_activity(ActivityStatus.EN_COURS)
        ActivityLifecycleService.transition(act, ActivityStatus.REALISE, self.user)
        act.refresh_from_db()
        self.assertEqual(act.status, ActivityStatus.REALISE)

    def test_valid_transition_realise_to_cloture(self):
        from activity.models import QuarterlyExecution
        act = self._create_activity(ActivityStatus.REALISE)
        # Add execution data (required by validation)
        sa = act.sous_activites.first()
        QuarterlyExecution.objects.create(
            sous_activite=sa, quarter=1, year=2025,
            budget_prevu=1000, budget_engage=800, budget_decaisse=600,
            resultats_attendus=10, resultats_realises=8,
        )
        ActivityLifecycleService.transition(act, ActivityStatus.CLOTURE, self.user)
        act.refresh_from_db()
        self.assertEqual(act.status, ActivityStatus.CLOTURE)
        self.assertIsNotNone(act.closed_by)

    def test_invalid_transition_planifie_to_en_cours(self):
        act = self._create_activity(ActivityStatus.PLANIFIE)
        with self.assertRaises(ValueError):
            ActivityLifecycleService.transition(act, ActivityStatus.EN_COURS, self.user)

    def test_invalid_transition_cloture_to_anything(self):
        act = self._create_activity(ActivityStatus.CLOTURE)
        with self.assertRaises(ValueError):
            ActivityLifecycleService.transition(act, ActivityStatus.EN_COURS, self.user)

    def test_revert_budgetise_to_planifie(self):
        act = self._create_activity(ActivityStatus.BUDGETISE)
        ActivityLifecycleService.transition(act, ActivityStatus.PLANIFIE, self.user)
        act.refresh_from_db()
        self.assertEqual(act.status, ActivityStatus.PLANIFIE)

    def test_reopen_realise_to_en_cours(self):
        act = self._create_activity(ActivityStatus.REALISE)
        ActivityLifecycleService.transition(act, ActivityStatus.EN_COURS, self.user)
        act.refresh_from_db()
        self.assertEqual(act.status, ActivityStatus.EN_COURS)

    def test_transition_creates_audit_trail(self):
        act = self._create_activity(ActivityStatus.PLANIFIE)
        ActivityLifecycleService.transition(act, ActivityStatus.BUDGETISE, self.user, 'Test comment')
        trail = ActivityStatusTransition.objects.filter(activite=act)
        self.assertEqual(trail.count(), 1)
        entry = trail.first()
        self.assertEqual(entry.from_status, ActivityStatus.PLANIFIE)
        self.assertEqual(entry.to_status, ActivityStatus.BUDGETISE)
        self.assertEqual(entry.comment, 'Test comment')

    def test_budgetise_requires_positive_budget(self):
        """Validation: cannot transition to BUDGETISE with zero budget."""
        act = Activite.objects.create(
            sous_composante=self.sc, code='A-NOBUDGET', name='No Budget',
            status=ActivityStatus.PLANIFIE,
        )
        # No sous-activites = no budget
        with self.assertRaises(ValueError):
            ActivityLifecycleService.transition(act, ActivityStatus.BUDGETISE, self.user)
