from decimal import Decimal
from datetime import date

from django.test import TestCase

from activity.models import (
    PTBA, PTBAStatus, Composante, SousComposante,
    Activite, ActivityStatus, SousActivite,
    FundingSource, SousActiviteFunding,
    QuarterlyExecution, RevisionStatus, WeeklyPlanEntry,
)


class PTBAModelTest(TestCase):
    def test_create_ptba(self):
        ptba = PTBA.objects.create(
            code='PTBA-TEST-2025',
            name='Test PTBA',
            fiscal_year_start=date(2024, 7, 1),
            fiscal_year_end=date(2025, 6, 30),
            status=PTBAStatus.DRAFT,
        )
        self.assertEqual(ptba.code, 'PTBA-TEST-2025')
        self.assertEqual(ptba.status, PTBAStatus.DRAFT)
        self.assertIsNotNone(ptba.id)

    def test_ptba_str(self):
        ptba = PTBA.objects.create(
            code='PTBA-2025',
            name='Annual Plan',
            fiscal_year_start=date(2024, 7, 1),
            fiscal_year_end=date(2025, 6, 30),
        )
        self.assertEqual(str(ptba), 'PTBA-2025 - Annual Plan')


class HierarchyModelTest(TestCase):
    def setUp(self):
        self.ptba = PTBA.objects.create(
            code='PTBA-HIER-TEST',
            name='Hierarchy Test',
            fiscal_year_start=date(2024, 7, 1),
            fiscal_year_end=date(2025, 6, 30),
        )
        self.composante = Composante.objects.create(
            ptba=self.ptba,
            code='1',
            name='Composante 1',
            sort_order=1,
        )
        self.sous_composante = SousComposante.objects.create(
            composante=self.composante,
            code='1.1',
            name='Sous-Composante 1.1',
            sort_order=1,
        )
        self.activite = Activite.objects.create(
            sous_composante=self.sous_composante,
            code='1.1.1',
            name='Test Activity',
            status=ActivityStatus.PLANIFIE,
        )

    def test_hierarchy_creation(self):
        self.assertEqual(self.ptba.composantes.count(), 1)
        self.assertEqual(self.composante.sous_composantes.count(), 1)
        self.assertEqual(self.sous_composante.activites.count(), 1)

    def test_cascade_delete(self):
        """Deleting PTBA should cascade to all children."""
        sa = SousActivite.objects.create(
            activite=self.activite,
            code='1.1.1.1',
            name='Test Line Item',
            budget_total=Decimal('1000000'),
        )
        self.ptba.delete()
        self.assertEqual(Composante.objects.filter(id=self.composante.id).count(), 0)
        self.assertEqual(SousComposante.objects.filter(id=self.sous_composante.id).count(), 0)
        self.assertEqual(Activite.objects.filter(id=self.activite.id).count(), 0)
        self.assertEqual(SousActivite.objects.filter(id=sa.id).count(), 0)

    def test_unique_together_composante(self):
        """Composante code must be unique within a PTBA."""
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Composante.objects.create(
                ptba=self.ptba,
                code='1',
                name='Duplicate Code',
            )


class SousActiviteModelTest(TestCase):
    def setUp(self):
        self.ptba = PTBA.objects.create(
            code='PTBA-SA-TEST',
            name='SA Test',
            fiscal_year_start=date(2024, 7, 1),
            fiscal_year_end=date(2025, 6, 30),
        )
        comp = Composante.objects.create(ptba=self.ptba, code='1', name='C1')
        sc = SousComposante.objects.create(composante=comp, code='1.1', name='SC1.1')
        self.activite = Activite.objects.create(
            sous_composante=sc, code='1.1.1', name='Act',
        )

    def test_budget_fields(self):
        sa = SousActivite.objects.create(
            activite=self.activite,
            code='1.1.1.1',
            name='Line Item',
            unit='Province',
            quantity_total=Decimal('6'),
            quantity_t1=Decimal('2'),
            quantity_t2=Decimal('2'),
            quantity_t3=Decimal('1'),
            quantity_t4=Decimal('1'),
            unit_cost=Decimal('50000'),
            budget_t1=Decimal('100000'),
            budget_t2=Decimal('100000'),
            budget_t3=Decimal('50000'),
            budget_t4=Decimal('50000'),
            budget_total=Decimal('300000'),
        )
        self.assertEqual(sa.budget_total, Decimal('300000'))
        self.assertEqual(sa.unit_cost, Decimal('50000'))


class FundingSourceModelTest(TestCase):
    def test_create_funding_source(self):
        fs = FundingSource.objects.create(
            code='BM',
            name='Banque Mondiale',
            is_active=True,
        )
        self.assertEqual(fs.code, 'BM')
        self.assertTrue(fs.is_active)

    def test_unique_code(self):
        from django.db import IntegrityError
        FundingSource.objects.create(code='UE', name='Union Europeenne')
        with self.assertRaises(IntegrityError):
            FundingSource.objects.create(code='UE', name='Duplicate')


class SousActiviteFundingModelTest(TestCase):
    def setUp(self):
        ptba = PTBA.objects.create(
            code='PTBA-FUND-TEST',
            name='Fund Test',
            fiscal_year_start=date(2024, 7, 1),
            fiscal_year_end=date(2025, 6, 30),
        )
        comp = Composante.objects.create(ptba=ptba, code='1', name='C1')
        sc = SousComposante.objects.create(composante=comp, code='1.1', name='SC1.1')
        act = Activite.objects.create(sous_composante=sc, code='1.1.1', name='Act')
        self.sa = SousActivite.objects.create(
            activite=act, code='1.1.1.1', name='Line',
            budget_total=Decimal('1000000'),
        )
        self.bm = FundingSource.objects.create(code='BM_T', name='BM Test')
        self.ue = FundingSource.objects.create(code='UE_T', name='UE Test')

    def test_funding_allocation(self):
        SousActiviteFunding.objects.create(
            sous_activite=self.sa,
            funding_source=self.bm,
            amount=Decimal('600000'),
        )
        SousActiviteFunding.objects.create(
            sous_activite=self.sa,
            funding_source=self.ue,
            amount=Decimal('400000'),
        )
        total = sum(
            alloc.amount for alloc in self.sa.funding_allocations.all()
        )
        self.assertEqual(total, Decimal('1000000'))

    def test_unique_together_funding(self):
        from django.db import IntegrityError
        SousActiviteFunding.objects.create(
            sous_activite=self.sa,
            funding_source=self.bm,
            amount=Decimal('500000'),
        )
        with self.assertRaises(IntegrityError):
            SousActiviteFunding.objects.create(
                sous_activite=self.sa,
                funding_source=self.bm,
                amount=Decimal('200000'),
            )


class QuarterlyExecutionModelTest(TestCase):
    def setUp(self):
        ptba = PTBA.objects.create(
            code='PTBA-EXEC-TEST',
            name='Exec Test',
            fiscal_year_start=date(2024, 7, 1),
            fiscal_year_end=date(2025, 6, 30),
        )
        comp = Composante.objects.create(ptba=ptba, code='1', name='C1')
        sc = SousComposante.objects.create(composante=comp, code='1.1', name='SC1.1')
        act = Activite.objects.create(sous_composante=sc, code='1.1.1', name='Act')
        self.sa = SousActivite.objects.create(
            activite=act, code='1.1.1.1', name='Line',
            budget_t1=Decimal('100000'),
            quantity_t1=Decimal('10'),
        )

    def test_create_execution(self):
        ex = QuarterlyExecution.objects.create(
            sous_activite=self.sa,
            quarter=1,
            year=2025,
            budget_prevu=Decimal('100000'),
            budget_engage=Decimal('80000'),
            budget_decaisse=Decimal('50000'),
            resultats_attendus=Decimal('10'),
            resultats_realises=Decimal('7'),
        )
        self.assertEqual(ex.quarter, 1)
        self.assertEqual(ex.year, 2025)

    def test_unique_together_execution(self):
        from django.db import IntegrityError
        QuarterlyExecution.objects.create(
            sous_activite=self.sa, quarter=1, year=2025,
        )
        with self.assertRaises(IntegrityError):
            QuarterlyExecution.objects.create(
                sous_activite=self.sa, quarter=1, year=2025,
            )


class ActivityStatusTransitionModelTest(TestCase):
    def test_create_transition(self):
        ptba = PTBA.objects.create(
            code='PTBA-TRANS-TEST',
            name='Trans Test',
            fiscal_year_start=date(2024, 7, 1),
            fiscal_year_end=date(2025, 6, 30),
        )
        comp = Composante.objects.create(ptba=ptba, code='1', name='C1')
        sc = SousComposante.objects.create(composante=comp, code='1.1', name='SC')
        act = Activite.objects.create(sous_composante=sc, code='1.1.1', name='Act')

        # This test just validates the model structure
        self.assertIsNotNone(act.id)
        self.assertEqual(act.status, ActivityStatus.PLANIFIE)


class RevisionTrackingModelTest(TestCase):
    """Tests for PTBA 2025-2026 revision tracking fields."""

    def setUp(self):
        self.ptba = PTBA.objects.create(
            code='PTBA-REV-TEST',
            name='Revision Test',
            fiscal_year_start=date(2025, 7, 1),
            fiscal_year_end=date(2026, 6, 30),
        )
        comp = Composante.objects.create(ptba=self.ptba, code='1', name='C1')
        sc = SousComposante.objects.create(composante=comp, code='1.1', name='SC1.1')
        self.activite = Activite.objects.create(
            sous_composante=sc, code='1.1.1', name='Act',
        )

    def test_activite_revision_status_default(self):
        self.assertEqual(self.activite.revision_status, 'INITIAL')
        self.assertEqual(self.activite.revision_comment, '')

    def test_activite_revision_status_set(self):
        self.activite.revision_status = RevisionStatus.REVISE
        self.activite.revision_comment = 'Budget revised'
        self.activite.save()
        self.activite.refresh_from_db()
        self.assertEqual(self.activite.revision_status, RevisionStatus.REVISE)
        self.assertEqual(self.activite.revision_comment, 'Budget revised')

    def test_sous_activite_initial_revised_fields(self):
        sa = SousActivite.objects.create(
            activite=self.activite,
            code='1.1.1.1',
            name='Line Item',
            quantity_total=Decimal('10'),
            unit_cost=Decimal('5000'),
            budget_total=Decimal('50000'),
            quantity_initial=Decimal('8'),
            quantity_revised=Decimal('10'),
            unit_cost_initial=Decimal('4000'),
            unit_cost_revised=Decimal('5000'),
            budget_initial=Decimal('32000'),
            budget_revised=Decimal('50000'),
        )
        self.assertEqual(sa.quantity_initial, Decimal('8'))
        self.assertEqual(sa.quantity_revised, Decimal('10'))
        self.assertEqual(sa.unit_cost_initial, Decimal('4000'))
        self.assertEqual(sa.unit_cost_revised, Decimal('5000'))
        self.assertEqual(sa.budget_initial, Decimal('32000'))
        self.assertEqual(sa.budget_revised, Decimal('50000'))

    def test_sous_activite_dates_and_responsibility(self):
        sa = SousActivite.objects.create(
            activite=self.activite,
            name='Task with dates',
            date_start=date(2025, 9, 1),
            date_end=date(2026, 3, 31),
            responsible='RIRIU',
            intervenants='RDO, RTM, RPs',
        )
        sa.refresh_from_db()
        self.assertEqual(sa.date_start, date(2025, 9, 1))
        self.assertEqual(sa.date_end, date(2026, 3, 31))
        self.assertEqual(sa.responsible, 'RIRIU')
        self.assertEqual(sa.intervenants, 'RDO, RTM, RPs')

    def test_sous_activite_revision_status(self):
        sa = SousActivite.objects.create(
            activite=self.activite,
            name='Abandoned task',
            revision_status=RevisionStatus.ABANDONNE,
            revision_comment='No longer needed',
        )
        sa.refresh_from_db()
        self.assertEqual(sa.revision_status, RevisionStatus.ABANDONNE)
        self.assertEqual(sa.revision_comment, 'No longer needed')

    def test_funding_initial_revised(self):
        sa = SousActivite.objects.create(
            activite=self.activite, name='Funded line',
            budget_total=Decimal('100000'),
        )
        fs = FundingSource.objects.create(code='D94400_T', name='IDA D94400 Test')
        alloc = SousActiviteFunding.objects.create(
            sous_activite=sa,
            funding_source=fs,
            amount=Decimal('80000'),
            amount_initial=Decimal('60000'),
            amount_revised=Decimal('80000'),
        )
        alloc.refresh_from_db()
        self.assertEqual(alloc.amount, Decimal('80000'))
        self.assertEqual(alloc.amount_initial, Decimal('60000'))
        self.assertEqual(alloc.amount_revised, Decimal('80000'))


class WeeklyPlanEntryModelTest(TestCase):
    """Tests for WeeklyPlanEntry model."""

    def setUp(self):
        ptba = PTBA.objects.create(
            code='PTBA-WEEK-TEST',
            name='Weekly Test',
            fiscal_year_start=date(2025, 7, 1),
            fiscal_year_end=date(2026, 6, 30),
        )
        comp = Composante.objects.create(ptba=ptba, code='1', name='C1')
        sc = SousComposante.objects.create(composante=comp, code='1.1', name='SC1.1')
        act = Activite.objects.create(sous_composante=sc, code='1.1.1', name='Act')
        self.sa = SousActivite.objects.create(
            activite=act, name='Task 1', responsible='RIRIU',
        )

    def test_create_weekly_entry(self):
        entry = WeeklyPlanEntry.objects.create(
            sous_activite=self.sa,
            week_start=date(2026, 3, 23),
            week_end=date(2026, 3, 27),
            planned_description='Plan for the week',
            status_description='Completed on Tuesday',
            status='REALISE',
            responsible='RIRIU',
            intervenants='RDO, RTM',
        )
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'REALISE')
        self.assertEqual(entry.week_start, date(2026, 3, 23))
        self.assertEqual(entry.week_end, date(2026, 3, 27))
        self.assertEqual(entry.responsible, 'RIRIU')

    def test_unique_together_weekly_entry(self):
        from django.db import IntegrityError
        WeeklyPlanEntry.objects.create(
            sous_activite=self.sa,
            week_start=date(2026, 3, 23),
            week_end=date(2026, 3, 27),
        )
        with self.assertRaises(IntegrityError):
            WeeklyPlanEntry.objects.create(
                sous_activite=self.sa,
                week_start=date(2026, 3, 23),
                week_end=date(2026, 3, 27),
            )

    def test_weekly_entry_str(self):
        entry = WeeklyPlanEntry.objects.create(
            sous_activite=self.sa,
            week_start=date(2026, 3, 23),
            week_end=date(2026, 3, 27),
        )
        self.assertEqual(str(entry), 'Task 1 - W2026-03-23')

    def test_weekly_status_choices(self):
        import datetime
        status_values = [s[0] for s in WeeklyPlanEntry.WeeklyStatus.choices]
        base_date = date(2026, 1, 5)  # A Monday
        for idx, status_value in enumerate(status_values):
            week_start = base_date + datetime.timedelta(weeks=idx)
            week_end = week_start + datetime.timedelta(days=4)
            entry = WeeklyPlanEntry.objects.create(
                sous_activite=self.sa,
                week_start=week_start,
                week_end=week_end,
                status=status_value,
            )
            self.assertEqual(entry.status, status_value)

    def test_cascade_delete_sous_activite(self):
        """Deleting a sous-activite cascades to weekly entries."""
        WeeklyPlanEntry.objects.create(
            sous_activite=self.sa,
            week_start=date(2026, 3, 23),
            week_end=date(2026, 3, 27),
        )
        sa_id = self.sa.id
        self.sa.delete()
        self.assertEqual(
            WeeklyPlanEntry.objects.filter(sous_activite_id=sa_id).count(), 0
        )
