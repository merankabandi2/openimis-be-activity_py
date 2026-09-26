"""UAT activity re-run 2026-09-26: ACT-B-R1 (PTBA rights granted to no role),
ACT-B-R3 (activities of a CLOSED PTBA stay editable), ACT-S7 (execution rate
of 1000 % or more overflows the rate columns)."""
import datetime
import io
import uuid
from decimal import Decimal

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from core.models import Role, RoleRight, User
from core.test_helpers import create_test_interactive_user
from activity.gql_mutations import (
    CreatePTBAMutation, CreateSousActiviteMutation, DeleteActiviteMutation,
    DeleteSousActiviteMutation, ReportQuarterlyExecutionMutation,
    UpdateActiviteMutation, UpdateSousActiviteMutation,
)
from activity.models import (
    PTBA, Activite, ActivityStatus, Composante, PTBAStatus, QuarterlyExecution,
    SousActivite, SousComposante,
)
from activity.services import QuarterlyExecutionService

LEGACY = [170001, 170002, 170003, 170004]
PTBA_RIGHTS = [170014, 170015, 170016, 170017]
ACTIVITY_RIGHTS = list(range(170005, 170014))


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


def live_rights(role):
    return sorted(RoleRight.objects.filter(role=role, validity_to__isnull=True)
                  .values_list('right_id', flat=True))


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


class GrantPtbaRightsTests(TestCase):
    """ACT-B-R1: grant_ptba_rights carries the legacy PTBA codes over to the
    PTBA rights 170014-170017 for activity roles only."""

    def setUp(self):
        self.gestion = make_role(LEGACY + ACTIVITY_RIGHTS)
        self.reader = make_role([170001, 170005, 170012])
        self.no_search = make_role([170002, 170003, 170004] + ACTIVITY_RIGHTS)
        self.beneficiary = make_role(LEGACY)
        self.activity_only = make_role([170005])
        self.already = make_role([170001, 170005, 170014])

    def _run(self, *args):
        out = io.StringIO()
        call_command('grant_ptba_rights', *args, stdout=out)
        return out.getvalue()

    def test_a_legacy_activity_role_can_manage_ptbas_after_apply(self):
        user = make_user(role=self.gestion)
        create = dict(name='x', fiscal_year_start=datetime.date(2026, 1, 1),
                      fiscal_year_end=datetime.date(2026, 12, 31))
        self.assertFalse(user.has_perms(['170014']))
        self.assertIsNotNone(CreatePTBAMutation.async_mutate(user, code='R1-BEFORE', **create))
        self.assertFalse(PTBA.objects.filter(code='R1-BEFORE').exists())

        self._run('--apply')

        user = User.objects.get(id=user.id)
        self.assertTrue(user.has_perms(['170014']))
        result = CreatePTBAMutation.async_mutate(user, code='R1-AFTER', **create)
        self.assertIsNone(result, error_text(result))
        self.assertTrue(PTBA.objects.filter(code='R1-AFTER').exists())

    def test_apply_maps_each_legacy_code_to_its_ptba_right(self):
        self._run('--apply')
        self.assertEqual(live_rights(self.gestion), sorted(LEGACY + ACTIVITY_RIGHTS + PTBA_RIGHTS))
        self.assertEqual(live_rights(self.reader), [170001, 170005, 170012, 170014])
        self.assertEqual(live_rights(self.no_search),
                         sorted([170002, 170003, 170004] + ACTIVITY_RIGHTS + [170015, 170016, 170017]))

    def test_roles_without_an_activity_right_are_untouched(self):
        self._run('--apply')
        self.assertEqual(live_rights(self.beneficiary), LEGACY)
        self.assertEqual(live_rights(self.activity_only), [170005])

    def test_legacy_rights_are_kept(self):
        self._run('--apply')
        self.assertTrue(set(LEGACY) <= set(live_rights(self.gestion)))

    def test_dry_run_is_the_default_and_writes_nothing(self):
        before = RoleRight.objects.count()
        output = self._run()
        self.assertEqual(RoleRight.objects.count(), before)
        self.assertIn('DRY RUN', output)
        self.assertIn(f'role {self.reader.id}, legacy [170001], to grant [170014], '
                      f'already held []', output)
        self.assertIn(f'role {self.already.id}, legacy [170001], to grant [], '
                      f'already held [170014]', output)

    def test_apply_and_dry_run_exclude_each_other(self):
        with self.assertRaises(CommandError):
            self._run('--apply', '--dry-run')

    def test_second_run_creates_nothing(self):
        self._run('--apply')
        count = RoleRight.objects.count()
        output = self._run('--apply')
        self.assertEqual(RoleRight.objects.count(), count)
        self.assertIn('rights created 0', output)

    def test_a_closed_role_is_skipped(self):
        self.reader.validity_to = datetime.datetime.now()
        self.reader.save()
        self._run('--apply')
        self.assertNotIn(170014, live_rights(self.reader))

    def test_cached_rights_of_a_logged_in_user_are_purged(self):
        user = make_user(role=self.reader)
        i_user = user.i_user
        self.assertNotIn(170014, i_user.rights)
        self.assertIsNotNone(cache.get(f'rights_{i_user.id}'))

        output = self._run('--apply')

        self.assertIsNone(cache.get(f'rights_{i_user.id}'))
        self.assertIn(170014, i_user.rights)
        self.assertIn('rights cache purged for 1 user(s)', output)


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
