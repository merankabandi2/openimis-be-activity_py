"""Activity-level fixes (UAT activity 2026-09-25: ACT-S5, ACT-S13, DEF-F-02,
ACT-D-N4, DEF-E-02, DEF-E-04)."""
import datetime
import uuid
from decimal import Decimal
from unittest import mock

from django.test import RequestFactory, TestCase
from graphene.test import Client

from core.models import Role, RoleRight
from core.test_helpers import create_test_interactive_user
from activity.dashboard_service import PTBADashboardService
from activity.gql_mutations import (
    BeginRevisionMutation, RejectRevisionMutation, TransitionActivityMutation,
    UpdateSousActiviteMutation, UpdateWeeklyPlanEntryMutation,
)
from activity.models import (
    PTBA, Activite, ActivityStatus, Composante, QuarterlyExecution, SousActivite,
    SousComposante, WeeklyPlanEntry,
)
from activity.services import QuarterlyExecutionService
from activity.validation import validate_budget_consistency

ALL_RIGHTS = list(range(802005, 802018))


def make_user(rights):
    now = datetime.datetime.now()
    tag = uuid.uuid4().hex[:8]
    role = Role.objects.create(
        name=f'UAT-ACT-{tag}', is_system=0, is_blocked=False, audit_user_id=-1, validity_from=now,
    )
    for right_id in rights:
        RoleRight.objects.create(role=role, right_id=right_id, audit_user_id=-1, validity_from=now)
    return create_test_interactive_user(username=f'uat_act_{tag}', roles=[role.id])


def error_text(result):
    if not result:
        return None
    return ' | '.join(f"{e.get('message', '')} {e.get('detail', '')}" for e in result)


def run_query(user, query):
    from openIMIS.schema import schema
    request = RequestFactory().post('/api/graphql')
    request.user = user
    return Client(schema).execute(query, context_value=request)


def quarters(sa, prefix):
    return [getattr(sa, f'{prefix}_t{i}') for i in (1, 2, 3, 4)]


class ActivityFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = make_user(ALL_RIGHTS)
        tag = uuid.uuid4().hex[:6]
        cls.ptba = PTBA.objects.create(
            code=f'UAT-ACT-{tag}', name='UAT', fiscal_year_start=datetime.date(2026, 1, 1),
            fiscal_year_end=datetime.date(2026, 12, 31),
        )
        cls.comp = Composante.objects.create(ptba=cls.ptba, code='1', name='Comp 1')
        cls.comp2 = Composante.objects.create(ptba=cls.ptba, code='2', name='Comp 2')
        cls.sc = SousComposante.objects.create(composante=cls.comp, code='1.1', name='SC 1')
        cls.sc2 = SousComposante.objects.create(composante=cls.comp2, code='2.1', name='SC 2')

    def activity(self, status=ActivityStatus.EN_COURS, n_sa=1, sc=None):
        act = Activite.objects.create(
            sous_composante=sc or self.sc, code=f'A-{uuid.uuid4().hex[:6]}', name='Activite', status=status,
        )
        lines = []
        for i in range(n_sa):
            lines.append(SousActivite.objects.create(
                activite=act, code=f'{act.code}-{i + 1}', name=f'SA{i + 1}', unit='atelier',
                quantity_total=Decimal('40'), quantity_t1=Decimal('10'), quantity_t2=Decimal('10'),
                quantity_t3=Decimal('10'), quantity_t4=Decimal('10'), unit_cost=Decimal('100'),
                budget_t1=Decimal('1000'), budget_t2=Decimal('1000'),
                budget_t3=Decimal('1000'), budget_t4=Decimal('1000'), budget_total=Decimal('4000'),
            ))
        return act, lines


class FeedIndicatorsTests(ActivityFixtures):
    """ACT-S5: an indicator's quarter achievement is the sum over its linked
    executions, and a manual achievement is left untouched."""

    def _indicator(self):
        from merankabandi.models import Indicator
        return Indicator.objects.create(name='UAT indicator', baseline=Decimal('0'), target=Decimal('100'))

    def test_two_sous_activites_of_one_quarter_are_summed(self):
        from merankabandi.models import IndicatorAchievement
        act, (sa1, sa2) = self.activity(n_sa=2)
        indicator = self._indicator()
        act.indicators.add(indicator)
        QuarterlyExecutionService.report(sa1, 1, 2026, self.user, resultats_realises=Decimal('10'))
        QuarterlyExecutionService.report(sa2, 1, 2026, self.user, resultats_realises=Decimal('25'))
        rows = IndicatorAchievement.objects.filter(indicator=indicator, date=datetime.date(2026, 3, 31))
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().achieved, Decimal('35'))
        QuarterlyExecutionService.report(sa1, 1, 2026, self.user, resultats_realises=Decimal('12'))
        self.assertEqual(rows.get().achieved, Decimal('37'))

    def test_manual_achievement_on_the_quarter_end_is_kept(self):
        from merankabandi.models import IndicatorAchievement
        act, (sa1,) = self.activity()
        indicator = self._indicator()
        act.indicators.add(indicator)
        manual = IndicatorAchievement.objects.create(
            indicator=indicator, date=datetime.date(2026, 3, 31), achieved=Decimal('999'), comment='manual')
        QuarterlyExecutionService.report(sa1, 1, 2026, self.user, resultats_realises=Decimal('10'))
        manual.refresh_from_db()
        self.assertEqual(manual.achieved, Decimal('999'))
        self.assertEqual(manual.comment, 'manual')
        auto = IndicatorAchievement.objects.exclude(id=manual.id).get(indicator=indicator)
        self.assertEqual(auto.achieved, Decimal('10'))


class RejectRevisionTests(ActivityFixtures):
    """ACT-S13: rejecting a revision restores T1-T4 with the totals."""

    def test_reject_restores_quarters_and_keeps_the_line_editable(self):
        _, (sa,) = self.activity()
        self.assertIsNone(BeginRevisionMutation.async_mutate(self.user, sous_activite_id=str(sa.id)))
        result = UpdateSousActiviteMutation.async_mutate(
            self.user, id=str(sa.id),
            quantity_t1=Decimal('30'), quantity_t2=Decimal('10'), quantity_t3=Decimal('10'), quantity_t4=Decimal('10'),
            quantity_total=Decimal('60'), budget_t1=Decimal('3000'), budget_t2=Decimal('1000'),
            budget_t3=Decimal('1000'), budget_t4=Decimal('1000'), budget_total=Decimal('6000'),
        )
        self.assertIsNone(result, error_text(result))
        self.assertIsNone(RejectRevisionMutation.async_mutate(self.user, sous_activite_id=str(sa.id)))
        sa.refresh_from_db()
        self.assertEqual(sa.budget_total, Decimal('4000'))
        self.assertEqual(quarters(sa, 'budget'), [Decimal('1000')] * 4)
        self.assertEqual(quarters(sa, 'quantity'), [Decimal('10')] * 4)
        self.assertIsNone(validate_budget_consistency(sa))
        result = UpdateSousActiviteMutation.async_mutate(self.user, id=str(sa.id), name='renamed')
        self.assertIsNone(result, error_text(result))

    def test_reject_without_snapshot_resplits_the_restored_totals(self):
        _, (sa,) = self.activity()
        sa.quantity_initial, sa.unit_cost_initial, sa.budget_initial = Decimal('40'), Decimal('100'), Decimal('4000')
        sa.quantity_t1, sa.budget_t1, sa.quantity_total, sa.budget_total = (
            Decimal('30'), Decimal('3000'), Decimal('60'), Decimal('6000'))
        sa.revision_status = 'REVISE'
        sa.save()
        self.assertIsNone(RejectRevisionMutation.async_mutate(self.user, sous_activite_id=str(sa.id)))
        sa.refresh_from_db()
        self.assertEqual(sa.budget_total, Decimal('4000'))
        self.assertIsNone(validate_budget_consistency(sa))


class SousActiviteLabelUpdateTests(ActivityFixtures):
    """DEF-F-02: an update that sets no budget field leaves the stored budget
    as it is, even on an imported line whose quarters differ from its total."""

    def test_label_update_of_an_inconsistent_imported_line(self):
        _, (sa,) = self.activity()
        SousActivite.objects.filter(id=sa.id).update(budget_total=Decimal('5000'), quantity_total=Decimal('50'))
        result = UpdateSousActiviteMutation.async_mutate(self.user, id=str(sa.id), responsible='Coordinateur')
        self.assertIsNone(result, error_text(result))
        sa.refresh_from_db()
        self.assertEqual(sa.responsible, 'Coordinateur')
        self.assertEqual(sa.budget_total, Decimal('5000'))

    def test_budget_update_must_stay_consistent(self):
        _, (sa,) = self.activity()
        result = UpdateSousActiviteMutation.async_mutate(self.user, id=str(sa.id), budget_total=Decimal('9999'))
        self.assertIsNotNone(result)
        sa.refresh_from_db()
        self.assertEqual(sa.budget_total, Decimal('4000'))


class TransitionNotificationTests(ActivityFixtures):
    """ACT-D-N4: the notification context carries the {location} and {date}
    placeholders of the activity.* templates."""

    def test_submitted_context_has_location_and_date(self):
        act, _ = self.activity(status=ActivityStatus.BUDGETISE)
        act.province = 'Gitega'
        act.save()
        with mock.patch('notification.services.NotificationService.notify') as notify:
            result = TransitionActivityMutation.async_mutate(
                self.user, activite_id=str(act.id), to_status=ActivityStatus.EN_COURS)
        self.assertIsNone(result, error_text(result))
        context = notify.call_args.kwargs['context']
        self.assertEqual(context['location'], 'Gitega')
        self.assertRegex(context['date'], r'^\d{2}/\d{2}/\d{4}$')
        from notification.models import NotificationTemplate
        from notification.seed_data import FRENCH_TEMPLATES
        subject, body, sms = FRENCH_TEMPLATES['activity.submitted']
        _, rendered, _ = NotificationTemplate(subject=subject, body=body, sms_body=sms).render(context)
        self.assertNotIn('{', rendered)


class WeeklyEntryWithoutCreatorTests(ActivityFixtures):
    """DEF-E-02: an imported weekly entry (created_by NULL) can be updated."""

    def test_update_of_an_entry_without_created_by(self):
        _, (sa,) = self.activity()
        entry = WeeklyPlanEntry.objects.create(
            sous_activite=sa, week_start=datetime.date(2026, 3, 23), week_end=datetime.date(2026, 3, 27),
            created_by=None,
        )
        result = UpdateWeeklyPlanEntryMutation.async_mutate(self.user, id=str(entry.id), status='EN_COURS')
        self.assertIsNone(result, error_text(result))
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'EN_COURS')


class ComposanteQuarterlyDashboardTests(ActivityFixtures):
    """DEF-E-04: each composante row carries its own T1-T4 rates."""

    def test_composante_quarterly_rates_are_per_composante(self):
        _, (sa1,) = self.activity()
        _, (sa2,) = self.activity(sc=self.sc2)
        QuarterlyExecutionService.report(sa1, 1, 2026, self.user, resultats_realises=Decimal('1'))
        QuarterlyExecutionService.report(sa2, 1, 2026, self.user, resultats_realises=Decimal('0.5'))
        QuarterlyExecutionService.report(sa2, 2, 2026, self.user, resultats_realises=Decimal('1'))
        rows = {r['composante_code']: r for r in PTBADashboardService._get_composante_performance(self.ptba)}
        q1 = {q['quarter']: q['taux_realisation'] for q in rows['1']['quarterly']}
        q2 = {q['quarter']: q['taux_realisation'] for q in rows['2']['quarterly']}
        self.assertEqual(q1, {1: Decimal('10')})
        self.assertEqual(q2, {1: Decimal('5'), 2: Decimal('10')})


class DashboardQueryTests(ActivityFixtures):
    """DEF-E-04 through the ptbaDashboard field the dashboard page queries."""

    def test_ptba_dashboard_returns_quarters_per_composante(self):
        _, (sa1,) = self.activity()
        _, (sa2,) = self.activity(sc=self.sc2)
        QuarterlyExecutionService.report(sa1, 1, 2026, self.user, resultats_realises=Decimal('1'))
        QuarterlyExecutionService.report(sa2, 2, 2026, self.user, resultats_realises=Decimal('1'))
        result = run_query(self.user, '{ ptbaDashboard(ptbaId: "%s") { composantePerformance '
                                      '{ composanteCode budgetEngage quarterly { quarter tauxRealisation } } } }'
                           % self.ptba.id)
        self.assertIsNone(result.get('errors'), result)
        rows = {r['composanteCode']: r['quarterly'] for r in result['data']['ptbaDashboard']['composantePerformance']}
        self.assertEqual([q['quarter'] for q in rows['1']], [1])
        self.assertEqual([q['quarter'] for q in rows['2']], [2])


class ActivityPageQueryTests(ActivityFixtures):
    """ACT-S2 through the activite query of the activity page, for an account
    holding only PTBA search, activity search and dashboard view."""

    def test_activity_page_reads_indicator_achievements(self):
        from merankabandi.models import Indicator, IndicatorAchievement
        from django.apps import apps
        config = apps.get_app_config('activity')
        reader = make_user([int(c) for name in ('gql_ptba_search_perms', 'gql_activity_search_perms',
                                                'gql_dashboard_view_perms') for c in getattr(config, name)])
        act, _ = self.activity()
        indicator = Indicator.objects.create(name='UAT indicator', baseline=Decimal('0'), target=Decimal('100'))
        act.indicators.add(indicator)
        IndicatorAchievement.objects.create(indicator=indicator, date=datetime.date(2026, 3, 31), achieved=Decimal('12'))
        result = run_query(reader, '{ activite(id: "%s") { edges { node { id indicators { edges { node '
                                   '{ id name baseline target achievements { edges { node { achieved date timestamp } } } } } } } } } }'
                           % act.id)
        self.assertIsNone(result.get('errors'), result)
        node = result['data']['activite']['edges'][0]['node']
        achievements = node['indicators']['edges'][0]['node']['achievements']['edges']
        self.assertEqual([a['node']['achieved'] for a in achievements], ['12.00'])
