"""UAT activity re-run 2026-09-26: ACT-B-R3 (activities of a CLOSED PTBA stay
editable), ACT-S7 (execution rate of 1000 % or more overflows the rate
columns)."""
import datetime
import uuid
from decimal import Decimal

from django.test import TestCase

from core.models import Role, RoleRight
from core.test_helpers import create_test_interactive_user
from activity.gql_mutations import (
    CreateSousActiviteMutation, DeleteActiviteMutation,
    DeleteSousActiviteMutation, ReportQuarterlyExecutionMutation,
    UpdateActiviteMutation, UpdateSousActiviteMutation,
)
from activity.models import (
    PTBA, Activite, ActivityStatus, Composante, PTBAStatus, QuarterlyExecution,
    SousActivite, SousComposante,
)
from activity.services import QuarterlyExecutionService

PTBA_RIGHTS = [802014, 802015, 802016, 802017]
ACTIVITY_RIGHTS = list(range(802005, 802014))


def make_role(rights):
    now = datetime.datetime.now()
    role = Role.objects.create(
        name=f'UAT-R0926-{uuid.uuid4().hex[:8]}', is_system=0, is_blocked=False,
        audit_user_id=-1, validity_from=now,
    )
    for right_id in rights:
        RoleRight.objects.create(role=role, right_id=right_id, audit_user_id=-1, validity_from=now)
    return role


def make_user(rights=None, role=None):
    role = role or make_role(rights)
    return create_test_interactive_user(
        username=f'uat_r0926_{uuid.uuid4().hex[:8]}', roles=[role.id])


def error_text(result):
    if not result:
        return None
    return ' | '.join(f"{e.get('message', '')} {e.get('detail', '')}" for e in result)


def make_ptba(code, status=PTBAStatus.DRAFT):
    return PTBA.objects.create(
        code=code, name=f'PTBA {code}', status=status,
        fiscal_year_start=datetime.date(2026, 1, 1),
        fiscal_year_end=datetime.date(2026, 12, 31),
    )


def make_hierarchy(code, status):
    ptba = make_ptba(code, status=status)
    comp = Composante.objects.create(ptba=ptba, code='K1', name='K1')
    sc = SousComposante.objects.create(composante=comp, code='K1.1', name='K1.1')
    act = Activite.objects.create(sous_composante=sc, code='KA1', name='activity')
    sa = SousActivite.objects.create(activite=act, code='KA1.1', name='sub-activity')
    return ptba, sc, act, sa


class ClosedPtbaActivityTests(TestCase):
    """ACT-B-R3: the activities and sous-activites of a CLOSED PTBA are
    read-only. The user holds every activity right, so a refusal comes from
    the invariant, which each test checks by message."""

    @classmethod
    def setUpTestData(cls):
        cls.user = make_user(ACTIVITY_RIGHTS)

    def setUp(self):
        self.closed, self.closed_sc, self.closed_act, self.closed_sa = make_hierarchy(
            f'R3-CL-{uuid.uuid4().hex[:6]}', PTBAStatus.CLOSED)
        self.open, self.open_sc, self.open_act, self.open_sa = make_hierarchy(
            f'R3-OP-{uuid.uuid4().hex[:6]}', PTBAStatus.ACTIVE)

    def assertRefused(self, result):
        self.assertIsNotNone(result)
        self.assertIn('is closed', error_text(result))

    def test_update_activite_refused(self):
        self.assertRefused(UpdateActiviteMutation.async_mutate(
            self.user, id=str(self.closed_act.id), name='renamed'))
        self.closed_act.refresh_from_db()
        self.assertEqual(self.closed_act.name, 'activity')

    def test_update_activite_cannot_move_it_into_a_closed_ptba(self):
        self.assertRefused(UpdateActiviteMutation.async_mutate(
            self.user, id=str(self.open_act.id), sous_composante_id=str(self.closed_sc.id)))
        self.open_act.refresh_from_db()
        self.assertEqual(self.open_act.sous_composante_id, self.open_sc.id)

    def test_delete_activite_refused_and_no_listed_activity_is_deleted(self):
        self.assertRefused(DeleteActiviteMutation.async_mutate(
            self.user, ids=[str(self.open_act.id), str(self.closed_act.id)]))
        self.assertTrue(Activite.objects.filter(id=self.closed_act.id).exists())
        self.assertTrue(Activite.objects.filter(id=self.open_act.id).exists())

    def test_create_sous_activite_refused(self):
        self.assertRefused(CreateSousActiviteMutation.async_mutate(
            self.user, activite_id=str(self.closed_act.id), code='KA1.2', name='new'))
        self.assertEqual(SousActivite.objects.filter(activite=self.closed_act).count(), 1)

    def test_update_sous_activite_refused(self):
        self.assertRefused(UpdateSousActiviteMutation.async_mutate(
            self.user, id=str(self.closed_sa.id), name='renamed'))
        self.closed_sa.refresh_from_db()
        self.assertEqual(self.closed_sa.name, 'sub-activity')

    def test_update_sous_activite_cannot_move_it_into_a_closed_ptba(self):
        self.assertRefused(UpdateSousActiviteMutation.async_mutate(
            self.user, id=str(self.open_sa.id), activite_id=str(self.closed_act.id)))
        self.open_sa.refresh_from_db()
        self.assertEqual(self.open_sa.activite_id, self.open_act.id)

    def test_delete_sous_activite_refused_and_no_listed_line_is_deleted(self):
        self.assertRefused(DeleteSousActiviteMutation.async_mutate(
            self.user, ids=[str(self.open_sa.id), str(self.closed_sa.id)]))
        self.assertTrue(SousActivite.objects.filter(id=self.closed_sa.id).exists())
        self.assertTrue(SousActivite.objects.filter(id=self.open_sa.id).exists())

    def test_activities_of_an_open_ptba_stay_editable(self):
        result = UpdateActiviteMutation.async_mutate(
            self.user, id=str(self.open_act.id), name='renamed')
        self.assertIsNone(result, error_text(result))
        result = UpdateSousActiviteMutation.async_mutate(
            self.user, id=str(self.open_sa.id), name='renamed')
        self.assertIsNone(result, error_text(result))
        result = CreateSousActiviteMutation.async_mutate(
            self.user, activite_id=str(self.open_act.id), code='KA1.2', name='new')
        self.assertIsNone(result, error_text(result))
        result = DeleteActiviteMutation.async_mutate(self.user, ids=[str(self.open_act.id)])
        self.assertIsNone(result, error_text(result))
        self.assertFalse(Activite.objects.filter(id=self.open_act.id).exists())


class ExecutionRateTests(TestCase):
    """ACT-S7: execution rates of 1000 % or more are stored."""

    @classmethod
    def setUpTestData(cls):
        cls.user = make_user(ACTIVITY_RIGHTS)

    def setUp(self):
        _, _, act, sa = make_hierarchy(f'S7-{uuid.uuid4().hex[:6]}', PTBAStatus.ACTIVE)
        act.status = ActivityStatus.EN_COURS
        act.save()
        sa.budget_t3 = Decimal('1500')
        sa.quantity_t3 = Decimal('2')
        sa.save()
        self.sa = sa

    def test_rate_of_1000_percent_is_saved_through_the_mutation(self):
        result = ReportQuarterlyExecutionMutation.async_mutate(
            self.user, sous_activite_id=str(self.sa.id), quarter=3, year=2026,
            budget_engage=Decimal('15000'), budget_decaisse=Decimal('1500'),
            resultats_realises=Decimal('40'))
        self.assertIsNone(result, error_text(result))
        execution = QuarterlyExecution.objects.get(sous_activite=self.sa, quarter=3, year=2026)
        self.assertEqual(execution.taux_engagement, Decimal('1000.00'))
        self.assertEqual(execution.taux_decaissement, Decimal('100.00'))
        self.assertEqual(execution.taux_realisation, Decimal('2000.00'))

    def test_rate_beyond_the_column_capacity_is_refused_with_a_clear_message(self):
        self.sa.budget_t3 = Decimal('0.01')
        self.sa.save()
        with self.assertRaises(ValueError) as refusal:
            QuarterlyExecutionService.report(
                self.sa, 3, 2026, self.user, budget_engage=Decimal('1000000000000'))
        self.assertIn('taux_engagement', str(refusal.exception))
        self.assertFalse(QuarterlyExecution.objects.filter(sous_activite=self.sa).exists())

    def test_rate_beyond_the_column_capacity_is_reported_by_the_mutation(self):
        self.sa.budget_t3 = Decimal('0.01')
        self.sa.save()
        result = ReportQuarterlyExecutionMutation.async_mutate(
            self.user, sous_activite_id=str(self.sa.id), quarter=3, year=2026,
            budget_engage=Decimal('1000000000000'))
        text = error_text(result) or ''
        self.assertIn('taux_engagement', text)
        self.assertNotIn('numeric field overflow', text)
        self.assertFalse(QuarterlyExecution.objects.filter(sous_activite=self.sa).exists())
