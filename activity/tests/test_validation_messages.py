"""Refusal messages name the sous-activite they are about."""
from decimal import Decimal

from django.test import TestCase
from core.test_helpers import LogInHelper

from activity.models import (
    PTBA, Composante, SousComposante, Activite, SousActivite,
    FundingSource, SousActiviteFunding, ActivityStatus,
)
from activity.validation import (
    validate_budget_consistency,
    validate_funding_allocation,
    validate_transition_preconditions,
)


class ValidationMessageLabelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = LogInHelper().get_or_create_user_api(username='validation_msg_test')
        ptba = PTBA.objects.create(
            code='PTBA-VM', name='Validation messages',
            fiscal_year_start='2026-01-01', fiscal_year_end='2026-12-31',
            user_created=user, user_updated=user,
        )
        comp = Composante.objects.create(ptba=ptba, code='1', name='C')
        sc = SousComposante.objects.create(composante=comp, code='1.1', name='SC')
        cls.activite = Activite.objects.create(
            sous_composante=sc, code='A-VM', name='A', status=ActivityStatus.REALISE,
        )
        cls.source = FundingSource.objects.create(code='SRC-VM', name='Source')

    def _line(self, code, name='Atelier de lancement'):
        return SousActivite.objects.create(
            activite=self.activite, code=code, name=name, unit='atelier',
            budget_total=Decimal('1000'), budget_t1=Decimal('1000'),
        )

    def test_blank_code_funding_refusal_names_the_line(self):
        sa = self._line('')
        SousActiviteFunding.objects.create(
            sous_activite=sa, funding_source=self.source, amount=Decimal('5000'),
        )
        self.assertTrue(validate_funding_allocation(sa).endswith(' for Atelier de lancement'))

    def test_blank_code_budget_refusal_names_the_line(self):
        sa = self._line('')
        sa.budget_t1 = Decimal('10')
        self.assertTrue(validate_budget_consistency(sa).endswith(' for Atelier de lancement'))

    def test_blank_code_closure_refusal_names_the_line(self):
        self._line('')
        errors = validate_transition_preconditions(self.activite, ActivityStatus.CLOTURE)
        self.assertEqual(
            errors,
            ['Sous-activite Atelier de lancement has no execution data. Consider reporting before closing.'],
        )

    def test_code_is_used_when_set(self):
        sa = self._line('SA-1')
        SousActiviteFunding.objects.create(
            sous_activite=sa, funding_source=self.source, amount=Decimal('5000'),
        )
        self.assertTrue(validate_funding_allocation(sa).endswith(' for SA-1'))
