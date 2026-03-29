from decimal import Decimal
from datetime import date

from django.test import TestCase

from activity.models import (
    PTBA, PTBAStatus, Composante, SousComposante,
    Activite, ActivityStatus, SousActivite,
    FundingSource, SousActiviteFunding, QuarterlyExecution,
)
from activity.dashboard_service import PTBADashboardService


class DashboardTestMixin:
    """Common setup for dashboard tests."""

    def _create_hierarchy(self, ptba_code='PTBA-DASH-TEST'):
        self.ptba = PTBA.objects.create(
            code=ptba_code,
            name='Dashboard Test PTBA',
            fiscal_year_start=date(2025, 1, 1),
            fiscal_year_end=date(2025, 12, 31),
            status=PTBAStatus.ACTIVE,
        )
        self.comp1 = Composante.objects.create(
            ptba=self.ptba, code='1', name='Composante 1', sort_order=1,
        )
        self.comp2 = Composante.objects.create(
            ptba=self.ptba, code='2', name='Composante 2', sort_order=2,
        )
        self.sc1 = SousComposante.objects.create(
            composante=self.comp1, code='1.1', name='SC 1.1', sort_order=1,
        )
        self.sc2 = SousComposante.objects.create(
            composante=self.comp2, code='2.1', name='SC 2.1', sort_order=1,
        )
        self.act1 = Activite.objects.create(
            sous_composante=self.sc1, code='1.1.1', name='Activity 1',
            status=ActivityStatus.EN_COURS,
        )
        self.act2 = Activite.objects.create(
            sous_composante=self.sc2, code='2.1.1', name='Activity 2',
            status=ActivityStatus.PLANIFIE,
        )
        self.sa1 = SousActivite.objects.create(
            activite=self.act1, code='1.1.1.1', name='Line 1',
            budget_total=Decimal('1000000'),
            budget_t1=Decimal('250000'), budget_t2=Decimal('250000'),
            budget_t3=Decimal('250000'), budget_t4=Decimal('250000'),
            quantity_total=Decimal('100'),
            quantity_t1=Decimal('25'), quantity_t2=Decimal('25'),
            quantity_t3=Decimal('25'), quantity_t4=Decimal('25'),
            unit_cost=Decimal('10000'),
        )
        self.sa2 = SousActivite.objects.create(
            activite=self.act2, code='2.1.1.1', name='Line 2',
            budget_total=Decimal('500000'),
            budget_t1=Decimal('125000'), budget_t2=Decimal('125000'),
            budget_t3=Decimal('125000'), budget_t4=Decimal('125000'),
            quantity_total=Decimal('50'),
            quantity_t1=Decimal('12'), quantity_t2=Decimal('13'),
            quantity_t3=Decimal('12'), quantity_t4=Decimal('13'),
            unit_cost=Decimal('10000'),
        )


class TestDashboardOverviewEmptyPTBA(TestCase):
    """Test dashboard overview when PTBA has no execution data."""

    def test_dashboard_overview_empty_ptba(self):
        ptba = PTBA.objects.create(
            code='PTBA-EMPTY',
            name='Empty PTBA',
            fiscal_year_start=date(2025, 1, 1),
            fiscal_year_end=date(2025, 12, 31),
        )
        result = PTBADashboardService.get_overview(ptba.id)

        self.assertEqual(result['budget_prevu'], Decimal('0'))
        self.assertEqual(result['budget_engage'], Decimal('0'))
        self.assertEqual(result['budget_decaisse'], Decimal('0'))
        self.assertEqual(result['taux_engagement'], Decimal('0'))
        self.assertEqual(result['taux_decaissement'], Decimal('0'))
        self.assertEqual(result['taux_realisation'], Decimal('0'))
        self.assertEqual(result['activities_by_status'], [])
        self.assertEqual(result['funding_breakdown'], [])
        self.assertEqual(result['composante_performance'], [])
        self.assertEqual(len(result['quarterly_trend']), 4)
        self.assertEqual(result['top_delayed_activities'], [])
        self.assertEqual(result['alerts'], [])


class TestDashboardOverviewWithExecutions(DashboardTestMixin, TestCase):
    """Test dashboard overview with execution data."""

    def setUp(self):
        self._create_hierarchy()
        # Create T1 execution for sa1
        QuarterlyExecution.objects.create(
            sous_activite=self.sa1,
            quarter=1, year=2025,
            budget_prevu=Decimal('250000'),
            budget_engage=Decimal('200000'),
            budget_decaisse=Decimal('150000'),
            resultats_attendus=Decimal('25'),
            resultats_realises=Decimal('20'),
            taux_engagement=Decimal('80.00'),
            taux_decaissement=Decimal('60.00'),
            taux_realisation=Decimal('80.00'),
        )
        # Create T2 execution for sa1
        QuarterlyExecution.objects.create(
            sous_activite=self.sa1,
            quarter=2, year=2025,
            budget_prevu=Decimal('250000'),
            budget_engage=Decimal('250000'),
            budget_decaisse=Decimal('200000'),
            resultats_attendus=Decimal('25'),
            resultats_realises=Decimal('25'),
            taux_engagement=Decimal('100.00'),
            taux_decaissement=Decimal('80.00'),
            taux_realisation=Decimal('100.00'),
        )

    def test_dashboard_overview_with_executions(self):
        result = PTBADashboardService.get_overview(self.ptba.id)

        # Total budget prevu = 250000 + 250000 = 500000
        self.assertEqual(result['budget_prevu'], Decimal('500000'))
        # Total budget engage = 200000 + 250000 = 450000
        self.assertEqual(result['budget_engage'], Decimal('450000'))
        # Total budget decaisse = 150000 + 200000 = 350000
        self.assertEqual(result['budget_decaisse'], Decimal('350000'))
        # taux_engagement = 450000/500000 * 100 = 90.00
        self.assertEqual(result['taux_engagement'], Decimal('90'))
        # taux_decaissement = 350000/500000 * 100 = 70.00
        self.assertEqual(result['taux_decaissement'], Decimal('70'))
        # resultats_attendus = 25+25 = 50, realises = 20+25 = 45
        # taux_realisation = 45/50 * 100 = 90
        self.assertEqual(result['taux_realisation'], Decimal('90'))

    def test_dashboard_overview_with_quarter_filter(self):
        result = PTBADashboardService.get_overview(self.ptba.id, quarter=1, year=2025)

        self.assertEqual(result['budget_prevu'], Decimal('250000'))
        self.assertEqual(result['budget_engage'], Decimal('200000'))
        self.assertEqual(result['taux_engagement'], Decimal('80'))


class TestDashboardFundingBreakdown(DashboardTestMixin, TestCase):
    """Test dashboard funding breakdown."""

    def setUp(self):
        self._create_hierarchy()
        self.bm = FundingSource.objects.create(code='BM', name='Banque Mondiale')
        self.ue = FundingSource.objects.create(code='UE', name='Union Europeenne')
        SousActiviteFunding.objects.create(
            sous_activite=self.sa1, funding_source=self.bm,
            amount=Decimal('600000'),
        )
        SousActiviteFunding.objects.create(
            sous_activite=self.sa1, funding_source=self.ue,
            amount=Decimal('400000'),
        )

    def test_dashboard_funding_breakdown(self):
        result = PTBADashboardService.get_overview(self.ptba.id)

        breakdown = result['funding_breakdown']
        self.assertEqual(len(breakdown), 2)

        # Sorted by amount descending
        bm_entry = next(e for e in breakdown if e['source_code'] == 'BM')
        ue_entry = next(e for e in breakdown if e['source_code'] == 'UE')

        self.assertEqual(bm_entry['amount'], Decimal('600000'))
        self.assertEqual(ue_entry['amount'], Decimal('400000'))

        # Percentages: BM = 60%, UE = 40%
        self.assertEqual(bm_entry['percentage'], Decimal('60'))
        self.assertEqual(ue_entry['percentage'], Decimal('40'))


class TestDashboardActivitiesByStatus(DashboardTestMixin, TestCase):
    """Test dashboard activities by status count."""

    def setUp(self):
        self._create_hierarchy()

    def test_dashboard_activities_by_status(self):
        result = PTBADashboardService.get_overview(self.ptba.id)

        by_status = result['activities_by_status']
        status_map = {item['status']: item['count'] for item in by_status}

        self.assertEqual(status_map.get(ActivityStatus.EN_COURS), 1)
        self.assertEqual(status_map.get(ActivityStatus.PLANIFIE), 1)


class TestDashboardQuarterlyTrend(DashboardTestMixin, TestCase):
    """Test dashboard quarterly trend data."""

    def setUp(self):
        self._create_hierarchy()
        # T1 execution
        QuarterlyExecution.objects.create(
            sous_activite=self.sa1,
            quarter=1, year=2025,
            budget_prevu=Decimal('250000'),
            budget_engage=Decimal('100000'),
            budget_decaisse=Decimal('50000'),
            resultats_attendus=Decimal('25'),
            resultats_realises=Decimal('10'),
        )
        # T3 execution
        QuarterlyExecution.objects.create(
            sous_activite=self.sa1,
            quarter=3, year=2025,
            budget_prevu=Decimal('250000'),
            budget_engage=Decimal('250000'),
            budget_decaisse=Decimal('200000'),
            resultats_attendus=Decimal('25'),
            resultats_realises=Decimal('22'),
        )

    def test_dashboard_quarterly_trend(self):
        result = PTBADashboardService.get_overview(self.ptba.id, year=2025)

        trend = result['quarterly_trend']
        self.assertEqual(len(trend), 4)

        # T1 should have data
        t1 = trend[0]
        self.assertEqual(t1['quarter'], 1)
        self.assertEqual(t1['taux_engagement'], Decimal('40'))  # 100k/250k
        self.assertEqual(t1['taux_decaissement'], Decimal('20'))  # 50k/250k
        self.assertEqual(t1['taux_realisation'], Decimal('40'))  # 10/25

        # T2 should be zero (no data)
        t2 = trend[1]
        self.assertEqual(t2['quarter'], 2)
        self.assertEqual(t2['taux_engagement'], Decimal('0'))
        self.assertEqual(t2['taux_decaissement'], Decimal('0'))
        self.assertEqual(t2['taux_realisation'], Decimal('0'))

        # T3 should have data
        t3 = trend[2]
        self.assertEqual(t3['quarter'], 3)
        self.assertEqual(t3['taux_engagement'], Decimal('100'))
        self.assertEqual(t3['taux_decaissement'], Decimal('80'))
        self.assertEqual(t3['taux_realisation'], Decimal('88'))  # 22/25


class TestDashboardAlerts(DashboardTestMixin, TestCase):
    """Test dashboard alerts for low-performing activities."""

    def setUp(self):
        self._create_hierarchy()
        # Create execution with low realisation for act1 (EN_COURS)
        QuarterlyExecution.objects.create(
            sous_activite=self.sa1,
            quarter=1, year=2025,
            budget_prevu=Decimal('250000'),
            budget_engage=Decimal('50000'),
            budget_decaisse=Decimal('25000'),
            resultats_attendus=Decimal('25'),
            resultats_realises=Decimal('5'),  # 20% realisation -> HIGH
        )

    def test_alerts_high_severity(self):
        result = PTBADashboardService.get_overview(self.ptba.id)

        alerts = result['alerts']
        # act1 is EN_COURS with 20% realisation -> HIGH alert
        # act2 is PLANIFIE, not EN_COURS -> no alert
        high_alerts = [a for a in alerts if a['severity'] == 'HIGH']
        self.assertEqual(len(high_alerts), 1)
        self.assertEqual(high_alerts[0]['activite_id'], self.act1.id)

    def test_alerts_no_expected_results(self):
        """EN_COURS activity with no resultats_attendus gets MEDIUM alert."""
        # Create a new EN_COURS activity with no expected results
        sc_extra = SousComposante.objects.create(
            composante=self.comp1, code='1.2', name='SC 1.2',
        )
        act_extra = Activite.objects.create(
            sous_composante=sc_extra, code='1.2.1', name='Extra Act',
            status=ActivityStatus.EN_COURS,
        )
        sa_extra = SousActivite.objects.create(
            activite=act_extra, code='1.2.1.1', name='Extra Line',
        )
        # Execution with zero attendus
        QuarterlyExecution.objects.create(
            sous_activite=sa_extra,
            quarter=1, year=2025,
            budget_prevu=Decimal('100000'),
            resultats_attendus=Decimal('0'),
            resultats_realises=Decimal('0'),
        )

        result = PTBADashboardService.get_overview(self.ptba.id)
        alerts = result['alerts']
        medium_alerts = [a for a in alerts if a['severity'] == 'MEDIUM' and a['activite_id'] == act_extra.id]
        self.assertEqual(len(medium_alerts), 1)


class TestComposanteSummary(DashboardTestMixin, TestCase):
    """Test per-composante summary."""

    def setUp(self):
        self._create_hierarchy()
        QuarterlyExecution.objects.create(
            sous_activite=self.sa1,
            quarter=1, year=2025,
            budget_prevu=Decimal('250000'),
            budget_engage=Decimal('200000'),
            budget_decaisse=Decimal('150000'),
            resultats_attendus=Decimal('25'),
            resultats_realises=Decimal('20'),
        )

    def test_composante_summary(self):
        result = PTBADashboardService.get_composante_summary(self.comp1.id)

        self.assertEqual(result['composante_code'], '1')
        self.assertEqual(result['budget_prevu'], Decimal('250000'))
        self.assertEqual(result['budget_decaisse'], Decimal('150000'))
        self.assertEqual(result['taux_decaissement'], Decimal('60'))
        self.assertEqual(result['taux_realisation'], Decimal('80'))

    def test_composante_summary_empty(self):
        """Composante with no executions returns zeros."""
        result = PTBADashboardService.get_composante_summary(self.comp2.id)

        self.assertEqual(result['budget_prevu'], Decimal('0'))
        self.assertEqual(result['taux_decaissement'], Decimal('0'))
        self.assertEqual(result['taux_realisation'], Decimal('0'))
