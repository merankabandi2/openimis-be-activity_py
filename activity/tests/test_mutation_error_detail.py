"""The detail of a refused activity mutation is the refusal text itself, not
the repr of the ValidationError message list."""
import datetime
import inspect
import json
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.gql.gql_mutations.base_mutation import BaseMutation
from core.models import MutationLog, Role, RoleRight
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext
from core.test_helpers import create_test_interactive_user

from activity import gql_mutations
from activity.gql_mutations import (
    AllocateFundingMutation,
    CreateComposanteMutation,
    TransitionActivityMutation,
)
from activity.models import (
    PTBA, PTBAStatus, Composante, SousComposante, Activite, SousActivite,
    FundingSource, SousActiviteFunding, ActivityStatus,
)

ACTIVITY_RIGHTS = list(range(170005, 170018))


def _user(username):
    now = datetime.datetime.now()
    role = Role.objects.create(
        name=f'ACT08 {username}', is_system=0, is_blocked=False, audit_user_id=-1, validity_from=now,
    )
    for right_id in ACTIVITY_RIGHTS:
        RoleRight.objects.create(role=role, right_id=right_id, audit_user_id=-1, validity_from=now)
    return create_test_interactive_user(username=username, roles=[role.id])


def _hierarchy(code, status=PTBAStatus.DRAFT):
    ptba = PTBA.objects.create(
        code=code, name=code, status=status,
        fiscal_year_start=datetime.date(2026, 1, 1), fiscal_year_end=datetime.date(2026, 12, 31),
    )
    comp = Composante.objects.create(ptba=ptba, code='1', name='C')
    sc = SousComposante.objects.create(composante=comp, code='1.1', name='SC')
    act = Activite.objects.create(sous_composante=sc, code=f'{code}-A', name='A')
    sa = SousActivite.objects.create(
        activite=act, code='SA-1', name='Atelier', unit='atelier',
        quantity_total=Decimal('1'), quantity_t1=Decimal('1'), unit_cost=Decimal('1000'),
        budget_t1=Decimal('1000'), budget_total=Decimal('1000'),
    )
    return ptba, act, sa


def _raising_mutation(error):
    from activity.gql_mutations import ActivityBaseMutation

    class RaisingMutation(ActivityBaseMutation):
        _mutation_class = 'RaisingMutation'
        _mutation_module = 'activity'

        class Meta:
            abstract = True

        @classmethod
        def _validate_mutation(cls, user, **data):
            pass

        @classmethod
        def _mutate(cls, user, **data):
            raise error

    return RaisingMutation


class ActivityBaseMutationTests(TestCase):
    def _detail(self, error):
        result = _raising_mutation(error).async_mutate(None)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['message'], 'Failed to process RaisingMutation mutation')
        return result[0]['detail']

    def test_single_message_is_returned_as_is(self):
        self.assertEqual(self._detail(ValidationError('Refused.')), 'Refused.')

    def test_message_list_is_joined(self):
        self.assertEqual(self._detail(ValidationError(['First.', 'Second.'])), 'First.; Second.')

    def test_field_errors_are_joined(self):
        detail = self._detail(ValidationError({'amount': ['Too high.'], 'code': ['Blank.']}))
        self.assertEqual(sorted(detail.split('; ')), ['Blank.', 'Too high.'])

    def test_other_exceptions_keep_their_text(self):
        self.assertEqual(self._detail(ValueError('Cannot transition.')), 'Cannot transition.')

    def test_every_activity_mutation_uses_the_activity_base(self):
        from activity.gql_mutations import ActivityBaseMutation
        mutations = [
            obj for _, obj in inspect.getmembers(gql_mutations, inspect.isclass)
            if issubclass(obj, BaseMutation) and obj is not BaseMutation
            and obj.__module__ == gql_mutations.__name__
        ]
        self.assertTrue(mutations)
        self.assertEqual([m.__name__ for m in mutations if not issubclass(m, ActivityBaseMutation)], [])


class ActivityRefusalDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _user(f'act08_{uuid.uuid4().hex[:6]}')
        cls.source = FundingSource.objects.create(code='ACT08-SRC', name='Source')

    def test_over_allocation_detail_has_no_brackets_and_is_rolled_back(self):
        _, _, sa = _hierarchy('ACT08-ALLOC')
        result = AllocateFundingMutation.async_mutate(
            self.user, sous_activite_id=str(sa.id), funding_source_id=str(self.source.id),
            amount=Decimal('5000'),
        )
        self.assertEqual(result[0]['detail'], 'Total funding (5000.00) exceeds budget total (1000.00) for SA-1')
        self.assertFalse(SousActiviteFunding.objects.filter(sous_activite=sa).exists())

    def test_closed_ptba_detail_has_no_brackets(self):
        ptba, _, _ = _hierarchy('ACT08-CLOSED', status=PTBAStatus.CLOSED)
        result = CreateComposanteMutation.async_mutate(
            self.user, ptba_id=str(ptba.id), code='2', name='C2',
        )
        self.assertEqual(result[0]['detail'], 'PTBA ACT08-CLOSED is closed and can no longer be modified.')
        self.assertEqual(ptba.composantes.count(), 1)

    def test_transition_refusal_detail_is_unchanged(self):
        _, act, _ = _hierarchy('ACT08-TRANS')
        act.sous_activites.all().delete()
        result = TransitionActivityMutation.async_mutate(
            self.user, activite_id=str(act.id), to_status=ActivityStatus.BUDGETISE,
        )
        self.assertEqual(
            result[0]['detail'],
            'Activity must have at least one sous-activite to be budgetised.; '
            'Activity must have a positive budget to be budgetised.',
        )


class ActivityRefusalMutationLogTests(openIMISGraphQLTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _user(f'act08g_{uuid.uuid4().hex[:6]}')
        cls.token = BaseTestContext(user=cls.user).get_jwt()
        cls.source = FundingSource.objects.create(code='ACT08-GQL', name='Source')

    def test_mutation_log_error_carries_the_plain_refusal(self):
        _, _, sa = _hierarchy('ACT08-GQL')
        cmid = str(uuid.uuid4())
        self.query(
            'mutation { allocateFunding(input: { clientMutationId: "%s" sousActiviteId: "%s" '
            'fundingSourceId: "%s" amount: "5000" }) { internalId } }' % (cmid, sa.id, self.source.id),
            headers={'HTTP_AUTHORIZATION': f'Bearer {self.token}'},
        )
        log = MutationLog.objects.get(client_mutation_id=cmid)
        self.assertEqual(log.status, MutationLog.ERROR)
        self.assertEqual(json.loads(log.error), [{
            'message': 'Failed to process AllocateFundingMutation mutation',
            'detail': 'Total funding (5000.00) exceeds budget total (1000.00) for SA-1',
        }])
