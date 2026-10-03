"""The achievement fed from a quarterly execution is dated the end of that
quarter of the activity's PTBA: a July-June PTBA has T1 = July to September
and T3 = January to March, whatever year the execution was reported under."""
import datetime
import uuid
from decimal import Decimal

from django.test import TestCase

from activity.models import PTBA, Activite, ActivityStatus, Composante, SousActivite, SousComposante
from activity.services import QuarterlyExecutionService
from activity.tests.test_uat_activity import ALL_RIGHTS, make_user


class PtbaQuarterDatesTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = make_user(ALL_RIGHTS)
        tag = uuid.uuid4().hex[:6]
        cls.ptba = PTBA.objects.create(
            code=f'PTBA-Q-{tag}', name='PTBA 2025-2026', fiscal_year_start=datetime.date(2025, 7, 1),
            fiscal_year_end=datetime.date(2026, 6, 30),
        )
        composante = Composante.objects.create(ptba=cls.ptba, code='1', name='Comp 1')
        cls.sous_composante = SousComposante.objects.create(composante=composante, code='1.1', name='SC 1')

    def _linked_sous_activite(self):
        from merankabandi.models import Indicator
        activite = Activite.objects.create(sous_composante=self.sous_composante, code=f'A-{uuid.uuid4().hex[:6]}',
                                           name='Activite', status=ActivityStatus.EN_COURS)
        sous_activite = SousActivite.objects.create(
            activite=activite, code=f'{activite.code}-1', name='SA1', unit='atelier',
            quantity_total=Decimal('40'), quantity_t1=Decimal('10'), quantity_t2=Decimal('10'),
            quantity_t3=Decimal('10'), quantity_t4=Decimal('10'), unit_cost=Decimal('100'),
            budget_t1=Decimal('1000'), budget_t2=Decimal('1000'), budget_t3=Decimal('1000'),
            budget_t4=Decimal('1000'), budget_total=Decimal('4000'),
        )
        indicator = Indicator.objects.create(name='PTBA quarter indicator', baseline=Decimal('0'),
                                             target=Decimal('100'))
        activite.indicators.add(indicator)
        return sous_activite, indicator

    def test_the_quarters_of_a_july_june_ptba(self):
        from activity.signals import ptba_quarter_end
        self.assertEqual([ptba_quarter_end(self.ptba, q) for q in (1, 2, 3, 4)], [
            datetime.date(2025, 9, 30), datetime.date(2025, 12, 31),
            datetime.date(2026, 3, 31), datetime.date(2026, 6, 30),
        ])

    def test_t1_and_t3_are_dated_in_the_ptba_year(self):
        from merankabandi.models import IndicatorAchievement
        sous_activite, indicator = self._linked_sous_activite()

        QuarterlyExecutionService.report(sous_activite, 1, 2025, self.user, resultats_realises=Decimal('4'))
        QuarterlyExecutionService.report(sous_activite, 3, 2026, self.user, resultats_realises=Decimal('6'))

        rows = IndicatorAchievement.objects.filter(indicator=indicator).order_by('date')
        self.assertEqual([(row.date, row.achieved, row.comment) for row in rows], [
            (datetime.date(2025, 9, 30), Decimal('4'), 'Auto: T1 2025'),
            (datetime.date(2026, 3, 31), Decimal('6'), 'Auto: T3 2026'),
        ])

    def test_a_row_written_at_the_calendar_quarter_end_is_moved_not_duplicated(self):
        from merankabandi.models import IndicatorAchievement
        sous_activite, indicator = self._linked_sous_activite()
        legacy = IndicatorAchievement.objects.create(indicator=indicator, date=datetime.date(2025, 3, 31),
                                                     achieved=Decimal('2'), comment='Auto: T1 2025')

        QuarterlyExecutionService.report(sous_activite, 1, 2025, self.user, resultats_realises=Decimal('5'))

        row = IndicatorAchievement.objects.get(indicator=indicator)
        self.assertEqual((row.id, row.date, row.achieved), (legacy.id, datetime.date(2025, 9, 30), Decimal('5')))
