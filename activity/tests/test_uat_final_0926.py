"""UAT activity final run 2026-09-26: ACT-B-F1. Under a CLOSED PTBA every
write on an activity and its sous-activites is refused: lifecycle
transitions, execution reports, revisions, funding allocations, indicator
links and weekly-plan entries."""
import datetime
import uuid
from decimal import Decimal

from django.test import TestCase

from activity.gql_mutations import (
    AllocateFundingMutation, AllocateFundingRevisedMutation,
    ApproveRevisionMutation, BeginRevisionMutation,
    CreateWeeklyPlanEntryMutation, DeallocateFundingMutation,
    DeleteWeeklyPlanEntryMutation, LinkActivityToIndicatorMutation,
    RejectRevisionMutation, ReportQuarterlyExecutionMutation,
    TransitionActivityMutation, UnlinkActivityFromIndicatorMutation,
    UpdateWeeklyPlanEntryMutation,
)
from activity.models import (
    ActivityStatus, ActivityStatusTransition, FundingSource, PTBAStatus,
    QuarterlyExecution, SousActiviteFunding, WeeklyPlanEntry,
)
from activity.services import ActivityLifecycleService, QuarterlyExecutionService
from activity.tests.test_uat_rerun_0926 import (
    ACTIVITY_RIGHTS, PTBA_RIGHTS, error_text, make_hierarchy, make_user,
)

MONDAY = datetime.date(2026, 1, 5)
FRIDAY = datetime.date(2026, 1, 9)


def budget(sa, amount=Decimal('400000')):
    sa.quantity_total = Decimal('4')
    sa.unit_cost = amount / 4
    sa.budget_total = amount
    sa.budget_t1 = amount
    sa.save()


def weekly_entry(sa):
    return WeeklyPlanEntry.objects.create(
        sous_activite=sa, week_start=MONDAY, week_end=FRIDAY, planned_description='plan')


class ClosedPtbaActivityWritesTests(TestCase):
    """The user holds every activity and PTBA right, so a refusal comes
    from the closed-PTBA invariant, which each test checks by message."""

    @classmethod
    def setUpTestData(cls):
        cls.user = make_user(ACTIVITY_RIGHTS + PTBA_RIGHTS)

    def setUp(self):
        self.closed, _, self.closed_act, self.closed_sa = make_hierarchy(
            f'F1-CL-{uuid.uuid4().hex[:6]}', PTBAStatus.CLOSED)
        self.open, _, self.open_act, self.open_sa = make_hierarchy(
            f'F1-OP-{uuid.uuid4().hex[:6]}', PTBAStatus.ACTIVE)
        budget(self.closed_sa)
        budget(self.open_sa)
        self.source = FundingSource.objects.create(
            code=f'F1-{uuid.uuid4().hex[:6]}', name='donor')

    def assertRefused(self, result):
        self.assertIsNotNone(result)
        self.assertIn('is closed', error_text(result))

    def assertAccepted(self, result):
        self.assertIsNone(result, error_text(result))

    # ---- lifecycle transitions ----

    def test_transition_refused(self):
        self.assertRefused(TransitionActivityMutation.async_mutate(
            self.user, activite_id=str(self.closed_act.id), to_status=ActivityStatus.BUDGETISE))
        self.closed_act.refresh_from_db()
        self.assertEqual(self.closed_act.status, ActivityStatus.PLANIFIE)
        self.assertFalse(ActivityStatusTransition.objects.filter(activite=self.closed_act).exists())

    def test_transition_service_refuses_every_caller(self):
        self.closed_act.status = ActivityStatus.REALISE
        self.closed_act.save()
        with self.assertRaisesMessage(Exception, 'is closed'):
            ActivityLifecycleService.transition(
                self.closed_act, ActivityStatus.EN_COURS, self.user)
        self.closed_act.refresh_from_db()
        self.assertEqual(self.closed_act.status, ActivityStatus.REALISE)

    # ---- execution reporting ----

    def test_report_execution_refused(self):
        self.closed_act.status = ActivityStatus.EN_COURS
        self.closed_act.save()
        self.assertRefused(ReportQuarterlyExecutionMutation.async_mutate(
            self.user, sous_activite_id=str(self.closed_sa.id), quarter=1, year=2026,
            budget_engage=Decimal('1000')))
        self.assertFalse(QuarterlyExecution.objects.filter(sous_activite=self.closed_sa).exists())

    def test_report_execution_service_refuses_every_caller(self):
        self.closed_act.status = ActivityStatus.EN_COURS
        self.closed_act.save()
        with self.assertRaisesMessage(Exception, 'is closed'):
            QuarterlyExecutionService.report(
                sous_activite=self.closed_sa, quarter=1, year=2026, user=self.user,
                budget_engage=Decimal('1000'))
        self.assertFalse(QuarterlyExecution.objects.filter(sous_activite=self.closed_sa).exists())

    # ---- revisions ----

    def test_begin_revision_refused(self):
        self.assertRefused(BeginRevisionMutation.async_mutate(
            self.user, sous_activite_id=str(self.closed_sa.id)))
        self.closed_sa.refresh_from_db()
        self.assertEqual(self.closed_sa.revision_status, 'INITIAL')
        self.assertEqual(self.closed_sa.budget_initial, Decimal('0'))

    def test_approve_revision_refused(self):
        self.closed_sa.revision_status = 'REVISE'
        self.closed_sa.save()
        self.assertRefused(ApproveRevisionMutation.async_mutate(
            self.user, sous_activite_id=str(self.closed_sa.id)))
        self.closed_sa.refresh_from_db()
        self.assertEqual(self.closed_sa.revision_status, 'REVISE')
        self.assertIsNone(self.closed_sa.budget_revised)

    def test_reject_revision_refused(self):
        self.closed_sa.revision_status = 'REVISE'
        self.closed_sa.save()
        self.assertRefused(RejectRevisionMutation.async_mutate(
            self.user, sous_activite_id=str(self.closed_sa.id)))
        self.closed_sa.refresh_from_db()
        self.assertEqual(self.closed_sa.revision_status, 'REVISE')
        self.assertEqual(self.closed_sa.budget_total, Decimal('400000'))

    # ---- funding ----

    def test_allocate_funding_refused(self):
        self.assertRefused(AllocateFundingMutation.async_mutate(
            self.user, sous_activite_id=str(self.closed_sa.id),
            funding_source_id=str(self.source.id), amount=Decimal('1000')))
        self.assertFalse(SousActiviteFunding.objects.filter(sous_activite=self.closed_sa).exists())

    def test_allocate_funding_revised_refused(self):
        self.assertRefused(AllocateFundingRevisedMutation.async_mutate(
            self.user, sous_activite_id=str(self.closed_sa.id),
            funding_source_id=str(self.source.id), amount=Decimal('1000')))
        self.assertFalse(SousActiviteFunding.objects.filter(sous_activite=self.closed_sa).exists())

    def test_deallocate_funding_refused_and_no_listed_allocation_is_deleted(self):
        closed_alloc = SousActiviteFunding.objects.create(
            sous_activite=self.closed_sa, funding_source=self.source, amount=Decimal('1000'))
        open_alloc = SousActiviteFunding.objects.create(
            sous_activite=self.open_sa, funding_source=self.source, amount=Decimal('1000'))
        self.assertRefused(DeallocateFundingMutation.async_mutate(
            self.user, ids=[str(open_alloc.id), str(closed_alloc.id)]))
        self.assertTrue(SousActiviteFunding.objects.filter(id=closed_alloc.id).exists())
        self.assertTrue(SousActiviteFunding.objects.filter(id=open_alloc.id).exists())

    # ---- indicator links ----

    def test_link_indicator_refused(self):
        from merankabandi.models import Indicator
        indicator = Indicator.objects.create(name='F1 indicator')
        self.assertRefused(LinkActivityToIndicatorMutation.async_mutate(
            self.user, activite_id=str(self.closed_act.id), indicator_id=indicator.id))
        self.assertFalse(self.closed_act.indicators.filter(id=indicator.id).exists())

    def test_unlink_indicator_refused(self):
        from merankabandi.models import Indicator
        indicator = Indicator.objects.create(name='F1 indicator')
        self.closed_act.indicators.add(indicator)
        self.assertRefused(UnlinkActivityFromIndicatorMutation.async_mutate(
            self.user, activite_id=str(self.closed_act.id), indicator_id=indicator.id))
        self.assertTrue(self.closed_act.indicators.filter(id=indicator.id).exists())

    # ---- weekly plan ----

    def test_create_weekly_entry_refused(self):
        self.assertRefused(CreateWeeklyPlanEntryMutation.async_mutate(
            self.user, sous_activite_id=str(self.closed_sa.id),
            week_start=MONDAY, week_end=FRIDAY, planned_description='plan'))
        self.assertFalse(WeeklyPlanEntry.objects.filter(sous_activite=self.closed_sa).exists())

    def test_update_weekly_entry_refused(self):
        entry = weekly_entry(self.closed_sa)
        self.assertRefused(UpdateWeeklyPlanEntryMutation.async_mutate(
            self.user, id=str(entry.id), planned_description='changed'))
        entry.refresh_from_db()
        self.assertEqual(entry.planned_description, 'plan')

    def test_update_weekly_entry_cannot_move_it_into_a_closed_ptba(self):
        entry = weekly_entry(self.open_sa)
        self.assertRefused(UpdateWeeklyPlanEntryMutation.async_mutate(
            self.user, id=str(entry.id), sous_activite_id=str(self.closed_sa.id)))
        entry.refresh_from_db()
        self.assertEqual(entry.sous_activite_id, self.open_sa.id)

    def test_delete_weekly_entries_refused_and_no_listed_entry_is_deleted(self):
        closed_entry = weekly_entry(self.closed_sa)
        open_entry = weekly_entry(self.open_sa)
        self.assertRefused(DeleteWeeklyPlanEntryMutation.async_mutate(
            self.user, ids=[str(open_entry.id), str(closed_entry.id)]))
        self.assertTrue(WeeklyPlanEntry.objects.filter(id=closed_entry.id).exists())
        self.assertTrue(WeeklyPlanEntry.objects.filter(id=open_entry.id).exists())

    # ---- open PTBA controls ----

    def test_writes_under_an_open_ptba_are_accepted(self):
        from merankabandi.models import Indicator
        indicator = Indicator.objects.create(name='F1 indicator')
        self.assertAccepted(BeginRevisionMutation.async_mutate(
            self.user, sous_activite_id=str(self.open_sa.id)))
        self.assertAccepted(RejectRevisionMutation.async_mutate(
            self.user, sous_activite_id=str(self.open_sa.id)))
        self.assertAccepted(AllocateFundingMutation.async_mutate(
            self.user, sous_activite_id=str(self.open_sa.id),
            funding_source_id=str(self.source.id), amount=Decimal('1000')))
        alloc = SousActiviteFunding.objects.get(sous_activite=self.open_sa)
        self.assertAccepted(DeallocateFundingMutation.async_mutate(self.user, ids=[str(alloc.id)]))
        self.assertAccepted(LinkActivityToIndicatorMutation.async_mutate(
            self.user, activite_id=str(self.open_act.id), indicator_id=indicator.id))
        self.assertAccepted(UnlinkActivityFromIndicatorMutation.async_mutate(
            self.user, activite_id=str(self.open_act.id), indicator_id=indicator.id))
        self.assertAccepted(CreateWeeklyPlanEntryMutation.async_mutate(
            self.user, sous_activite_id=str(self.open_sa.id),
            week_start=MONDAY, week_end=FRIDAY, planned_description='plan'))
        entry = WeeklyPlanEntry.objects.get(sous_activite=self.open_sa)
        self.assertAccepted(UpdateWeeklyPlanEntryMutation.async_mutate(
            self.user, id=str(entry.id), planned_description='changed'))
        self.assertAccepted(DeleteWeeklyPlanEntryMutation.async_mutate(self.user, ids=[str(entry.id)]))
        self.assertAccepted(TransitionActivityMutation.async_mutate(
            self.user, activite_id=str(self.open_act.id), to_status=ActivityStatus.BUDGETISE))
        self.assertAccepted(TransitionActivityMutation.async_mutate(
            self.user, activite_id=str(self.open_act.id), to_status=ActivityStatus.EN_COURS))
        self.assertAccepted(ReportQuarterlyExecutionMutation.async_mutate(
            self.user, sous_activite_id=str(self.open_sa.id), quarter=1, year=2026,
            budget_engage=Decimal('1000')))
        self.open_act.refresh_from_db()
        self.assertEqual(self.open_act.status, ActivityStatus.EN_COURS)
        self.assertTrue(QuarterlyExecution.objects.filter(sous_activite=self.open_sa).exists())
