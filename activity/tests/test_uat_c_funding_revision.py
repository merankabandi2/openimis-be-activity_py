"""
UAT section C (docs/metier/activites-uat.md): sous-activites, budget, funding
and revision, exercised through the GraphQL schema so that permission checks,
the atomic blocks and the MutationLog error path run as in production.

Each test asserts the expected product behaviour of its UAT row; a known gap
(ACT-Sn) therefore shows up as a failing test.
"""
import datetime
import json
import uuid
from decimal import Decimal

from core.models import MutationLog, Role, RoleRight
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext
from core.test_helpers import create_test_interactive_user

from activity.models import (
    PTBA, Composante, SousComposante, Activite, SousActivite, FundingSource,
    SousActiviteFunding, QuarterlyExecution, WeeklyPlanEntry,
)

ALL_ACTIVITY_RIGHTS = list(range(802005, 802018))


def _role_with_rights(name, rights):
    role = Role.objects.create(
        name=name, is_system=0, is_blocked=False, audit_user_id=-1,
        validity_from=datetime.datetime.now(),
    )
    for right_id in rights:
        RoleRight.objects.create(
            role=role, right_id=right_id, audit_user_id=-1,
            validity_from=datetime.datetime.now(),
        )
    return role


class UatSectionCTests(openIMISGraphQLTestCase):

    @classmethod
    def setUpTestData(cls):
        role = _role_with_rights("UAT C PTBA Gestion", ALL_ACTIVITY_RIGHTS)
        cls.user = create_test_interactive_user(username="uat_c_gest_test", roles=[role.id])
        cls.token = BaseTestContext(user=cls.user).get_jwt()

    def setUp(self):
        super().setUp()
        self.ptba = PTBA.objects.create(
            code="UAT-C-BE", name="UAT C backend",
            fiscal_year_start=datetime.date(2026, 7, 1),
            fiscal_year_end=datetime.date(2027, 6, 30),
        )
        comp = Composante.objects.create(ptba=self.ptba, code="1", name="C1")
        sc = SousComposante.objects.create(composante=comp, code="1.1", name="SC1.1")
        self.activite = Activite.objects.create(sous_composante=sc, code="1.1.1", name="Act")
        self.fs1 = FundingSource.objects.create(code="UAC-T1", name="Source T1")
        self.fs2 = FundingSource.objects.create(code="UAC-T2", name="Source T2")

    # -- helpers ---------------------------------------------------------

    def _post(self, mutation_name, args):
        cmid = str(uuid.uuid4())
        response = self.query(
            f"""mutation {{ {mutation_name}(input: {{ {args} clientMutationId: "{cmid}" }}) {{ internalId }} }}""",
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.token}"},
        )
        content = json.loads(response.content)
        log = MutationLog.objects.filter(client_mutation_id=cmid).first()
        return content, log

    def _ok(self, mutation_name, args):
        content, log = self._post(mutation_name, args)
        self.assertNotIn("errors", content, content)
        self.assertIsNotNone(log)
        self.assertEqual(log.status, MutationLog.SUCCESS, log.error)
        return log

    def _failed(self, mutation_name, args):
        content, log = self._post(mutation_name, args)
        self.assertNotIn("errors", content, content)
        self.assertIsNotNone(log)
        self.assertEqual(log.status, MutationLog.ERROR, "mutation unexpectedly succeeded")
        return log.error or ""

    def _sa(self, **kw):
        values = dict(
            activite=self.activite, code="SA", name="Sous-activite",
            quantity_t1=Decimal("1"), quantity_t2=Decimal("1"),
            quantity_t3=Decimal("1"), quantity_t4=Decimal("1"),
            quantity_total=Decimal("4"), unit_cost=Decimal("1000"),
            budget_t1=Decimal("1000"), budget_t2=Decimal("1000"),
            budget_t3=Decimal("1000"), budget_t4=Decimal("1000"),
            budget_total=Decimal("4000"),
        )
        values.update(kw)
        return SousActivite.objects.create(**values)

    # -- C5 --------------------------------------------------------------

    def test_c5_delete_source_with_allocation_refused(self):
        sa = self._sa()
        alloc = SousActiviteFunding.objects.create(
            sous_activite=sa, funding_source=self.fs1, amount=Decimal("1000"))
        error = self._failed("deleteFundingSource", f'ids: ["{self.fs1.id}"]')
        self.assertIn("funding_source.delete.has_allocations", error)
        self.assertIn("UAC-T1", error)
        self.assertTrue(FundingSource.objects.filter(id=self.fs1.id).exists())
        self.assertTrue(SousActiviteFunding.objects.filter(id=alloc.id).exists())

    # -- C6 (create as sent by SousActiviteTable.handleSaveRow) ----------

    def test_c6_create_sous_activite_with_computed_budgets(self):
        self._ok("createSousActivite", (
            f'activiteId: "{self.activite.id}" name: "C6" unit: "atelier" '
            'quantityTotal: "10" quantityT1: "1" quantityT2: "2" quantityT3: "3" quantityT4: "4" '
            'unitCost: "2500" budgetT1: "2500" budgetT2: "5000" budgetT3: "7500" budgetT4: "10000" '
            'budgetTotal: "25000" sortOrder: 0 quantityInitial: "0" quantityRevised: "0" '
            'unitCostInitial: "0" unitCostRevised: "0" budgetInitial: "0" budgetRevised: "0" '
            'revisionStatus: "INITIAL"'
        ))
        sa = SousActivite.objects.get(activite=self.activite, name="C6")
        self.assertEqual(sa.budget_total, Decimal("25000"))
        self.assertEqual(
            sa.budget_t1 + sa.budget_t2 + sa.budget_t3 + sa.budget_t4, sa.budget_total)

    # -- C7 --------------------------------------------------------------

    def test_c7_update_quantities_consistent_accepted(self):
        sa = self._sa()
        self._ok("updateSousActivite", (
            f'id: "{sa.id}" name: "Sous-activite" quantityTotal: "8" quantityT1: "2" quantityT2: "2" '
            'quantityT3: "2" quantityT4: "2" unitCost: "1000" budgetT1: "2000" '
            'budgetT2: "2000" budgetT3: "2000" budgetT4: "2000" budgetTotal: "8000"'
        ))
        sa.refresh_from_db()
        self.assertEqual(sa.budget_total, Decimal("8000"))

    def test_c7_update_quarters_not_summing_to_total_refused(self):
        sa = self._sa()
        error = self._failed("updateSousActivite", (
            f'id: "{sa.id}" name: "Sous-activite" budgetT1: "2000" budgetT2: "1000" budgetT3: "1000" '
            'budgetT4: "1000" budgetTotal: "4000"'
        ))
        self.assertIn("do not sum to total", error)
        sa.refresh_from_db()
        self.assertEqual(sa.budget_t1, Decimal("1000"))

    # -- C8 --------------------------------------------------------------

    def test_c8_decimal_unit_cost_accepted(self):
        # JS float arithmetic sends 0.1 * 3 as 0.30000000000000004.
        sa = self._sa()
        self._ok("updateSousActivite", (
            f'id: "{sa.id}" name: "Sous-activite" quantityTotal: "3" quantityT1: "3" quantityT2: "0" '
            'quantityT3: "0" quantityT4: "0" unitCost: "0.1" '
            'budgetT1: "0.30000000000000004" budgetT2: "0" budgetT3: "0" budgetT4: "0" '
            'budgetTotal: "0.30000000000000004"'
        ))
        sa.refresh_from_db()
        self.assertEqual(sa.unit_cost, Decimal("0.10"))
        self.assertEqual(sa.budget_total, Decimal("0.30"))

    # -- C9 --------------------------------------------------------------

    def test_c9_delete_sous_activite_cascades(self):
        sa = self._sa()
        alloc = SousActiviteFunding.objects.create(
            sous_activite=sa, funding_source=self.fs1, amount=Decimal("1000"))
        execution = QuarterlyExecution.objects.create(
            sous_activite=sa, quarter=1, year=2026)
        weekly = WeeklyPlanEntry.objects.create(
            sous_activite=sa, week_start=datetime.date(2026, 9, 21),
            week_end=datetime.date(2026, 9, 25))
        self._ok("deleteSousActivite", f'ids: ["{sa.id}"]')
        self.assertFalse(SousActivite.objects.filter(id=sa.id).exists())
        self.assertFalse(SousActiviteFunding.objects.filter(id=alloc.id).exists())
        self.assertFalse(QuarterlyExecution.objects.filter(id=execution.id).exists())
        self.assertFalse(WeeklyPlanEntry.objects.filter(id=weekly.id).exists())

    # -- C10 / C11 -------------------------------------------------------

    def test_c10_allocate_within_budget(self):
        sa = self._sa()
        self._ok("allocateFunding",
                 f'sousActiviteId: "{sa.id}" fundingSourceId: "{self.fs1.id}" amount: "3000"')
        self.assertEqual(
            SousActiviteFunding.objects.get(sous_activite=sa, funding_source=self.fs1).amount,
            Decimal("3000"))

    def test_c11_second_source_over_budget_refused_and_rolled_back(self):
        sa = self._sa()
        SousActiviteFunding.objects.create(
            sous_activite=sa, funding_source=self.fs1, amount=Decimal("3000"))
        error = self._failed("allocateFunding",
                             f'sousActiviteId: "{sa.id}" fundingSourceId: "{self.fs2.id}" amount: "1500"')
        self.assertIn("exceeds budget total", error)
        self.assertFalse(
            SousActiviteFunding.objects.filter(sous_activite=sa, funding_source=self.fs2).exists())
        self.assertEqual(
            SousActiviteFunding.objects.get(sous_activite=sa, funding_source=self.fs1).amount,
            Decimal("3000"))

    def test_c11_same_source_over_budget_refused_and_rolled_back(self):
        sa = self._sa()
        SousActiviteFunding.objects.create(
            sous_activite=sa, funding_source=self.fs1, amount=Decimal("3000"))
        error = self._failed("allocateFunding",
                             f'sousActiviteId: "{sa.id}" fundingSourceId: "{self.fs1.id}" amount: "5000"')
        self.assertIn("exceeds budget total", error)
        self.assertEqual(
            SousActiviteFunding.objects.get(sous_activite=sa, funding_source=self.fs1).amount,
            Decimal("3000"))

    # -- C12 -------------------------------------------------------------

    def test_c12_update_allocation_amount_as_sent_by_fe(self):
        # FundingAllocationTable sends sousActiviteId, fundingSourceId and
        # amount (actions.js formatAllocateFundingGQL); the mutation upserts
        # on (sous_activite, funding_source).
        sa = self._sa()
        alloc = SousActiviteFunding.objects.create(
            sous_activite=sa, funding_source=self.fs1, amount=Decimal("1000"))
        self._ok("allocateFunding", (
            f'sousActiviteId: "{sa.id}" '
            f'fundingSourceId: "{self.fs1.id}" amount: "2000"'
        ))
        alloc.refresh_from_db()
        self.assertEqual(alloc.amount, Decimal("2000"))
        self.assertEqual(SousActiviteFunding.objects.filter(sous_activite=sa).count(), 1)

    # -- C13 -------------------------------------------------------------

    def test_c13_deallocate(self):
        sa = self._sa()
        alloc = SousActiviteFunding.objects.create(
            sous_activite=sa, funding_source=self.fs1, amount=Decimal("1000"))
        self._ok("deallocateFunding", f'ids: ["{alloc.id}"]')
        self.assertFalse(SousActiviteFunding.objects.filter(id=alloc.id).exists())

    # -- C14 / C15 -------------------------------------------------------

    def test_c14_begin_revision_snapshots_initial_values(self):
        sa = self._sa()
        self._ok("beginRevision", f'sousActiviteId: "{sa.id}"')
        sa.refresh_from_db()
        self.assertEqual(sa.revision_status, "REVISE")
        self.assertEqual(sa.quantity_initial, Decimal("4"))
        self.assertEqual(sa.unit_cost_initial, Decimal("1000"))
        self.assertEqual(sa.budget_initial, Decimal("4000"))

    def test_c15_approve_revision_copies_current_values(self):
        sa = self._sa()
        self._ok("beginRevision", f'sousActiviteId: "{sa.id}"')
        self._ok("updateSousActivite", (
            f'id: "{sa.id}" name: "Sous-activite" quantityTotal: "6" quantityT1: "3" quantityT2: "1" '
            'quantityT3: "1" quantityT4: "1" unitCost: "1000" budgetT1: "3000" '
            'budgetT2: "1000" budgetT3: "1000" budgetT4: "1000" budgetTotal: "6000"'
        ))
        self._ok("approveRevision", f'sousActiviteId: "{sa.id}" comment: "ok C15"')
        sa.refresh_from_db()
        self.assertEqual(sa.revision_status, "INITIAL")
        self.assertEqual(sa.quantity_revised, Decimal("6"))
        self.assertEqual(sa.budget_revised, Decimal("6000"))
        self.assertEqual(sa.budget_initial, Decimal("4000"))
        self.assertEqual(sa.budget_revised - sa.budget_initial, Decimal("2000"))
        self.assertEqual(sa.revision_comment, "ok C15")

    def test_c15_approve_outside_revision_refused(self):
        sa = self._sa()
        error = self._failed("approveRevision", f'sousActiviteId: "{sa.id}"')
        self.assertIn("must be in REVISE status", error)

    # -- C16 -------------------------------------------------------------

    def test_c16_reject_revision_restores_totals_and_status(self):
        sa = self._sa()
        self._ok("beginRevision", f'sousActiviteId: "{sa.id}"')
        self._ok("updateSousActivite", (
            f'id: "{sa.id}" name: "Sous-activite" quantityTotal: "6" quantityT1: "3" quantityT2: "1" '
            'quantityT3: "1" quantityT4: "1" unitCost: "1000" budgetT1: "3000" '
            'budgetT2: "1000" budgetT3: "1000" budgetT4: "1000" budgetTotal: "6000"'
        ))
        self._ok("rejectRevision", f'sousActiviteId: "{sa.id}" reason: "non C16"')
        sa.refresh_from_db()
        self.assertEqual(sa.revision_status, "ABANDONNE")
        self.assertEqual(sa.revision_comment, "non C16")
        self.assertEqual(sa.quantity_total, Decimal("4"))
        self.assertEqual(sa.unit_cost, Decimal("1000"))
        self.assertEqual(sa.budget_total, Decimal("4000"))

    def test_c16_reject_revision_restores_quarters(self):
        sa = self._sa()
        self._ok("beginRevision", f'sousActiviteId: "{sa.id}"')
        self._ok("updateSousActivite", (
            f'id: "{sa.id}" name: "Sous-activite" quantityTotal: "6" quantityT1: "3" quantityT2: "1" '
            'quantityT3: "1" quantityT4: "1" unitCost: "1000" budgetT1: "3000" '
            'budgetT2: "1000" budgetT3: "1000" budgetT4: "1000" budgetTotal: "6000"'
        ))
        self._ok("rejectRevision", f'sousActiviteId: "{sa.id}"')
        sa.refresh_from_db()
        self.assertEqual(
            (sa.quantity_t1, sa.budget_t1), (Decimal("1"), Decimal("1000")),
            "T1 not restored by rejectRevision (ACT-S13)")
        self.assertEqual(
            sa.budget_t1 + sa.budget_t2 + sa.budget_t3 + sa.budget_t4, sa.budget_total)

    def test_c16_line_editable_after_reject(self):
        sa = self._sa()
        self._ok("beginRevision", f'sousActiviteId: "{sa.id}"')
        self._ok("updateSousActivite", (
            f'id: "{sa.id}" name: "Sous-activite" quantityTotal: "6" quantityT1: "3" quantityT2: "1" '
            'quantityT3: "1" quantityT4: "1" unitCost: "1000" budgetT1: "3000" '
            'budgetT2: "1000" budgetT3: "1000" budgetT4: "1000" budgetTotal: "6000"'
        ))
        self._ok("rejectRevision", f'sousActiviteId: "{sa.id}"')
        # A partial update (name only) validates the merged row.
        self._ok("updateSousActivite", f'id: "{sa.id}" name: "renamed after reject"')

    # -- C17 -------------------------------------------------------------

    def test_c17_allocate_funding_revised_records_both_amounts(self):
        sa = self._sa()
        self._ok("allocateFundingRevised", (
            f'sousActiviteId: "{sa.id}" fundingSourceId: "{self.fs1.id}" '
            'amount: "3500" amountInitial: "3000" amountRevised: "3500"'
        ))
        alloc = SousActiviteFunding.objects.get(sous_activite=sa, funding_source=self.fs1)
        self.assertEqual(alloc.amount, Decimal("3500"))
        self.assertEqual(alloc.amount_initial, Decimal("3000"))
        self.assertEqual(alloc.amount_revised, Decimal("3500"))

    def test_c17_allocate_funding_revised_over_budget_refused(self):
        sa = self._sa()
        SousActiviteFunding.objects.create(
            sous_activite=sa, funding_source=self.fs1, amount=Decimal("3000"),
            amount_initial=Decimal("3000"))
        error = self._failed("allocateFundingRevised", (
            f'sousActiviteId: "{sa.id}" fundingSourceId: "{self.fs1.id}" '
            'amount: "4500" amountInitial: "3000" amountRevised: "4500"'
        ))
        self.assertIn("exceeds budget total", error)
        alloc = SousActiviteFunding.objects.get(sous_activite=sa, funding_source=self.fs1)
        self.assertEqual(alloc.amount, Decimal("3000"))
        self.assertIsNone(alloc.amount_revised)
