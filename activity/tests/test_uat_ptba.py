"""PTBA rights, list queries and PTBA invariants (UAT activity 2026-09-25:
ACT-S3, ACT-S4, ACT-S12, ACT-B-D2, ACT-B-D3, ACT-B-D5)."""
import datetime
import uuid

from django.test import RequestFactory, TestCase
from graphene.test import Client

from core.models import Role, RoleRight
from core.test_helpers import create_test_interactive_user
from activity.gql_mutations import (
    CreateComposanteMutation, CreatePTBAMutation, DeleteComposanteMutation,
    DeletePTBAMutation, UpdatePTBAMutation,
)
from activity.models import (
    PTBA, Activite, ActivityStatusTransition, Composante, FundingSource,
    PTBAStatus, QuarterlyExecution, SousActivite, SousActiviteFunding,
    SousComposante, WeeklyPlanEntry,
)

BENEFICIARY_RIGHTS = [170001, 170002, 170003, 170004]
PTBA_RIGHTS = [802014, 802015, 802016, 802017]
ACTIVITY_SEARCH = [802005]


def configured_rights(*names):
    """Right codes the activity module is configured with for these perms."""
    from django.apps import apps
    config = apps.get_app_config('activity')
    return [int(code) for name in names for code in getattr(config, name)]


PTBA_PERMS = ('gql_ptba_search_perms', 'gql_ptba_create_perms', 'gql_ptba_update_perms', 'gql_ptba_delete_perms')


def make_user(rights):
    now = datetime.datetime.now()
    tag = uuid.uuid4().hex[:8]
    role = Role.objects.create(
        name=f'UAT-PTBA-{tag}', is_system=0, is_blocked=False, audit_user_id=-1, validity_from=now,
    )
    for right_id in rights:
        RoleRight.objects.create(role=role, right_id=right_id, audit_user_id=-1, validity_from=now)
    return create_test_interactive_user(username=f'uat_ptba_{tag}', roles=[role.id])


def error_text(result):
    """async_mutate returns None on success, else a list of {message, detail}."""
    if not result:
        return None
    return ' | '.join(f"{e.get('message', '')} {e.get('detail', '')}" for e in result)


def make_ptba(code, status=PTBAStatus.DRAFT):
    return PTBA.objects.create(
        code=code, name=f'PTBA {code}', status=status,
        fiscal_year_start=datetime.date(2026, 1, 1),
        fiscal_year_end=datetime.date(2026, 12, 31),
    )


def ptba_input(ptba, **overrides):
    data = {
        'id': str(ptba.id), 'code': ptba.code, 'name': ptba.name,
        'fiscal_year_start': ptba.fiscal_year_start, 'fiscal_year_end': ptba.fiscal_year_end,
    }
    data.update(overrides)
    return data


class PtbaRightsTests(TestCase):
    """ACT-S3: PTBA rights are 802014-802017, distinct from the
    social_protection beneficiary rights 170001-170004."""

    @classmethod
    def setUpTestData(cls):
        cls.beneficiary_user = make_user(BENEFICIARY_RIGHTS)
        cls.ptba_user = make_user(PTBA_RIGHTS)

    def test_beneficiary_rights_cannot_create_or_delete_a_ptba(self):
        result = CreatePTBAMutation.async_mutate(
            self.beneficiary_user, code='S3-BEN', name='x',
            fiscal_year_start=datetime.date(2026, 1, 1), fiscal_year_end=datetime.date(2026, 12, 31),
        )
        self.assertIsNotNone(result)
        self.assertFalse(PTBA.objects.filter(code='S3-BEN').exists())
        ptba = make_ptba('S3-DEL')
        self.assertIsNotNone(DeletePTBAMutation.async_mutate(self.beneficiary_user, ids=[str(ptba.id)]))
        self.assertTrue(PTBA.objects.filter(id=ptba.id).exists())

    def test_ptba_rights_create_and_delete_a_ptba(self):
        result = CreatePTBAMutation.async_mutate(
            self.ptba_user, code='S3-OK', name='x',
            fiscal_year_start=datetime.date(2026, 1, 1), fiscal_year_end=datetime.date(2026, 12, 31),
        )
        self.assertIsNone(result, error_text(result))
        ptba = PTBA.objects.get(code='S3-OK')
        self.assertIsNone(DeletePTBAMutation.async_mutate(self.ptba_user, ids=[str(ptba.id)]))
        self.assertFalse(PTBA.objects.filter(id=ptba.id).exists())

    def test_budgeting_an_activity_needs_the_ptba_update_right(self):
        from activity.services import ActivityLifecycleService
        self.assertEqual(
            ActivityLifecycleService.required_perms('PLANIFIE', 'BUDGETISE'), ['802016'])


class ListQueryRightsTests(TestCase):
    """ACT-S4: every list query requires a module search right."""

    FIELDS = {
        'ptba': PTBA_RIGHTS[:1],
        'composante': PTBA_RIGHTS[:1],
        'sousComposante': PTBA_RIGHTS[:1],
        'activite': ACTIVITY_SEARCH,
        'sousActivite': ACTIVITY_SEARCH,
        'fundingSource': ACTIVITY_SEARCH,
        'sousActiviteFunding': ACTIVITY_SEARCH,
        'quarterlyExecution': ACTIVITY_SEARCH,
        'activityStatusTransition': ACTIVITY_SEARCH,
        'weeklyPlanEntry': ACTIVITY_SEARCH,
    }

    @classmethod
    def setUpTestData(cls):
        cls.no_rights = make_user([])
        cls.beneficiary_user = make_user(BENEFICIARY_RIGHTS)
        cls.reader = make_user(configured_rights('gql_ptba_search_perms', 'gql_activity_search_perms'))
        ptba = make_ptba('S4-LIST')
        comp = Composante.objects.create(ptba=ptba, code='1', name='C')
        sc = SousComposante.objects.create(composante=comp, code='1.1', name='SC')
        act = Activite.objects.create(sous_composante=sc, code='1.1.1', name='A', status='EN_COURS')
        sa = SousActivite.objects.create(activite=act, code='1.1.1.1', name='SA')
        source = FundingSource.objects.create(code='S4FS', name='FS')
        SousActiviteFunding.objects.create(sous_activite=sa, funding_source=source, amount=1)
        QuarterlyExecution.objects.create(sous_activite=sa, quarter=1, year=2026)
        ActivityStatusTransition.objects.create(
            activite=act, from_status='BUDGETISE', to_status='EN_COURS', transitioned_by=cls.reader)
        WeeklyPlanEntry.objects.create(
            sous_activite=sa, week_start=datetime.date(2026, 3, 23), week_end=datetime.date(2026, 3, 27))

    def _query(self, user, field):
        from openIMIS.schema import schema
        request = RequestFactory().post('/api/graphql')
        request.user = user
        return Client(schema).execute('{ %s(first: 5) { totalCount } }' % field, context_value=request)

    def test_lists_are_refused_without_a_module_right(self):
        for user in (self.no_rights, self.beneficiary_user):
            for field in self.FIELDS:
                result = self._query(user, field)
                self.assertTrue(result.get('errors'), f'{field}: {result}')
                self.assertIsNone((result.get('data') or {}).get(field), field)

    def test_lists_are_returned_with_the_search_right(self):
        for field in self.FIELDS:
            result = self._query(self.reader, field)
            self.assertIsNone(result.get('errors'), f'{field}: {result}')
            self.assertGreaterEqual(result['data'][field]['totalCount'], 1, field)

    def test_ptba_selectors_of_the_weekly_plan_calendar_and_dashboard(self):
        """Pages gated on activity search (weekly plan, calendar) or dashboard
        view list the PTBAs in their selector."""
        for perm in ('gql_activity_search_perms', 'gql_dashboard_view_perms'):
            user = make_user(configured_rights(perm))
            result = self._query(user, 'ptba')
            self.assertIsNone(result.get('errors'), f'{perm}: {result}')
            self.assertGreaterEqual(result['data']['ptba']['totalCount'], 1, perm)

    def test_refusal_message_is_not_the_session_expiry_message(self):
        result = self._query(self.no_rights, 'ptba')
        message = result['errors'][0]['message'].lower()
        self.assertNotIn(message, ('unauthorized', 'user not authorized for this operation'))


class PtbaInvariantTests(TestCase):
    """ACT-S12, ACT-B-D2, ACT-B-D3, ACT-B-D5. The user holds every PTBA right,
    so a refusal comes from the invariant, which each test checks by message."""

    @classmethod
    def setUpTestData(cls):
        cls.user = make_user(configured_rights(*PTBA_PERMS))

    def assertRefused(self, result, text):
        self.assertIsNotNone(result)
        self.assertIn(text, error_text(result))

    def test_update_cannot_change_the_status(self):
        draft = make_ptba('S12-DRAFT')
        result = UpdatePTBAMutation.async_mutate(self.user, **ptba_input(draft, status='CLOSED'))
        self.assertRefused(result, 'use transitionPtba')
        draft.refresh_from_db()
        self.assertEqual(draft.status, PTBAStatus.DRAFT)
        active = make_ptba('S12-ACTIVE', status=PTBAStatus.ACTIVE)
        result = UpdatePTBAMutation.async_mutate(self.user, **ptba_input(active, status='DRAFT'))
        self.assertRefused(result, 'use transitionPtba')
        active.refresh_from_db()
        self.assertEqual(active.status, PTBAStatus.ACTIVE)

    def test_update_with_the_current_status_is_accepted(self):
        draft = make_ptba('S12-SAME')
        result = UpdatePTBAMutation.async_mutate(
            self.user, **ptba_input(draft, name='renamed', status='DRAFT'))
        self.assertIsNone(result, error_text(result))
        draft.refresh_from_db()
        self.assertEqual(draft.name, 'renamed')

    def test_create_stores_draft_only(self):
        result = CreatePTBAMutation.async_mutate(
            self.user, code='S12-NEW', name='x', status='BOGUS',
            fiscal_year_start=datetime.date(2026, 1, 1), fiscal_year_end=datetime.date(2026, 12, 31),
        )
        self.assertRefused(result, 'created in DRAFT status')
        self.assertFalse(PTBA.objects.filter(code='S12-NEW').exists())

    def test_closed_ptba_cannot_be_updated(self):
        closed = make_ptba('BD2-CLOSED', status=PTBAStatus.CLOSED)
        result = UpdatePTBAMutation.async_mutate(self.user, **ptba_input(closed, name='renamed'))
        self.assertRefused(result, 'is closed')
        closed.refresh_from_db()
        self.assertEqual(closed.name, 'PTBA BD2-CLOSED')

    def test_closed_ptba_hierarchy_cannot_be_changed(self):
        closed = make_ptba('BD2-HIER', status=PTBAStatus.CLOSED)
        comp = Composante.objects.create(ptba=closed, code='1', name='C')
        self.assertRefused(CreateComposanteMutation.async_mutate(
            self.user, ptba_id=str(closed.id), code='2', name='C2'), 'is closed')
        self.assertRefused(DeleteComposanteMutation.async_mutate(self.user, ids=[str(comp.id)]), 'is closed')
        self.assertEqual(Composante.objects.filter(ptba=closed).count(), 1)

    def test_closed_ptba_cannot_be_deleted(self):
        closed = make_ptba('BD3-CLOSED', status=PTBAStatus.CLOSED)
        Composante.objects.create(ptba=closed, code='1', name='C')
        self.assertRefused(DeletePTBAMutation.async_mutate(self.user, ids=[str(closed.id)]), 'is closed')
        self.assertTrue(PTBA.objects.filter(id=closed.id).exists())
        self.assertEqual(Composante.objects.filter(ptba=closed).count(), 1)

    def test_fiscal_year_end_before_start_is_refused(self):
        result = CreatePTBAMutation.async_mutate(
            self.user, code='BD5-NEW', name='x',
            fiscal_year_start=datetime.date(2026, 12, 31), fiscal_year_end=datetime.date(2026, 1, 1),
        )
        self.assertRefused(result, 'fiscal year end')
        self.assertFalse(PTBA.objects.filter(code='BD5-NEW').exists())
        ptba = make_ptba('BD5-UPD')
        result = UpdatePTBAMutation.async_mutate(
            self.user, **ptba_input(ptba, fiscal_year_end=datetime.date(2025, 1, 1)))
        self.assertRefused(result, 'fiscal year end')
        ptba.refresh_from_db()
        self.assertEqual(ptba.fiscal_year_end, datetime.date(2026, 12, 31))
