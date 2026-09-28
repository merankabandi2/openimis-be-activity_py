"""UAT section B (docs/metier/activites-uat.md): PTBA rows without a screen.

B10  updatePtba must not move a PTBA through its state machine.
B11  transitionPtba / approvePtba / closePtba refuse transitions outside
     DRAFT -> APPROVED -> ACTIVE -> CLOSED (and APPROVED -> DRAFT).
B24  createPtba / updatePtba store benefitPlanId.
B8   updatePtba leaves a CLOSED PTBA unchanged.
B9   updateActivite leaves an activity of a CLOSED PTBA unchanged.
The mutations go through the GraphQL endpoint and the mutation log, as the
FE sends them.
"""
import datetime

from django.conf import settings
from graphql_jwt.shortcuts import get_token

from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext
from core.test_helpers import create_test_role, LogInHelper
from social_protection.models import BenefitPlan

from activity.models import PTBA, PTBAStatus


class UatSectionBPtbaTest(openIMISGraphQLTestCase):
    GRAPHQL_URL = f"/{settings.SITE_ROOT()}graphql"
    GRAPHQL_SCHEMA = True

    @classmethod
    def setUpTestData(cls):
        role = create_test_role(
            perm_names=[
                'gql_ptba_search_perms', 'gql_ptba_create_perms',
                'gql_ptba_update_perms', 'gql_ptba_delete_perms',
            ],
            name="UatSectionBPtbaRole",
        )
        cls.user = LogInHelper().get_or_create_user_api(username='uat_b_ptba', roles=[role.id])
        cls.token = get_token(cls.user, BaseTestContext(user=cls.user))
        cls.benefit_plan = BenefitPlan(
            code="UATB24", name="UAT B24 plan", max_beneficiaries=0,
            ceiling_per_beneficiary="0.00",
            beneficiary_data_schema={"$schema": "https://json-schema.org/draft/2019-09/schema"},
            date_valid_from="2026-01-01", date_valid_to="2026-12-31",
        )
        cls.benefit_plan.save(username=cls.user.username)

    def _ptba(self, code, status=PTBAStatus.DRAFT):
        return PTBA.objects.create(
            code=code, name=f"PTBA {code}", status=status,
            fiscal_year_start=datetime.date(2026, 1, 1),
            fiscal_year_end=datetime.date(2026, 12, 31),
            user_created=self.user, user_updated=self.user,
        )

    def _mutation_error(self, mutation_type, params):
        """Sends the mutation; returns the mutation-log error text, or None on success."""
        try:
            self.send_mutation(mutation_type, params, self.token)
        except ValueError as exc:
            return str(exc)
        return None

    # --- B10 ---

    def test_b10_update_ptba_with_status_does_not_skip_the_state_machine(self):
        ptba = self._ptba("UAT-B10")
        self._mutation_error("updatePtba", {
            "id": str(ptba.id), "code": ptba.code, "name": ptba.name,
            "fiscalYearStart": "2026-01-01", "fiscalYearEnd": "2026-12-31",
            "status": "CLOSED",
        })
        ptba.refresh_from_db()
        self.assertEqual(ptba.status, PTBAStatus.DRAFT)

    def test_b10_update_ptba_with_status_does_not_revert_an_approval(self):
        ptba = self._ptba("UAT-B10R", status=PTBAStatus.ACTIVE)
        self._mutation_error("updatePtba", {
            "id": str(ptba.id), "code": ptba.code, "name": "renamed",
            "fiscalYearStart": "2026-01-01", "fiscalYearEnd": "2026-12-31",
            "status": "DRAFT",
        })
        ptba.refresh_from_db()
        self.assertEqual(ptba.status, PTBAStatus.ACTIVE)

    # --- B11 ---

    def test_b11_transition_draft_to_active_refused(self):
        ptba = self._ptba("UAT-B11A")
        error = self._mutation_error("transitionPtba", {"ptbaId": str(ptba.id), "toStatus": "ACTIVE"})
        self.assertIsNotNone(error)
        self.assertIn("Cannot transition PTBA from DRAFT to ACTIVE", error)
        ptba.refresh_from_db()
        self.assertEqual(ptba.status, PTBAStatus.DRAFT)

    def test_b11_transition_out_of_closed_refused(self):
        ptba = self._ptba("UAT-B11C", status=PTBAStatus.CLOSED)
        for target in ("DRAFT", "APPROVED", "ACTIVE"):
            error = self._mutation_error("transitionPtba", {"ptbaId": str(ptba.id), "toStatus": target})
            self.assertIsNotNone(error, target)
            self.assertIn(f"Cannot transition PTBA from CLOSED to {target}", error)
        ptba.refresh_from_db()
        self.assertEqual(ptba.status, PTBAStatus.CLOSED)

    def test_b11_transition_draft_to_closed_refused(self):
        ptba = self._ptba("UAT-B11D")
        error = self._mutation_error("transitionPtba", {"ptbaId": str(ptba.id), "toStatus": "CLOSED"})
        self.assertIn("Cannot transition PTBA from DRAFT to CLOSED", error or "")

    def test_b11_transition_unknown_status_refused(self):
        ptba = self._ptba("UAT-B11U")
        error = self._mutation_error("transitionPtba", {"ptbaId": str(ptba.id), "toStatus": "ARCHIVED"})
        self.assertIn("Invalid target PTBA status: ARCHIVED", error or "")

    def test_b11_approve_and_close_refuse_wrong_source_status(self):
        active = self._ptba("UAT-B11AP", status=PTBAStatus.ACTIVE)
        draft = self._ptba("UAT-B11CL")
        approve_error = self._mutation_error("approvePtba", {"ptbaId": str(active.id)})
        close_error = self._mutation_error("closePtba", {"ptbaId": str(draft.id)})
        self.assertIn("PTBA must be in DRAFT status to approve", approve_error or "")
        self.assertIn("PTBA must be in ACTIVE status to close", close_error or "")
        active.refresh_from_db()
        draft.refresh_from_db()
        self.assertEqual(active.status, PTBAStatus.ACTIVE)
        self.assertEqual(draft.status, PTBAStatus.DRAFT)

    def test_b11_valid_chain_accepted(self):
        ptba = self._ptba("UAT-B11OK")
        for target in ("APPROVED", "DRAFT", "APPROVED", "ACTIVE", "CLOSED"):
            self.assertIsNone(
                self._mutation_error("transitionPtba", {"ptbaId": str(ptba.id), "toStatus": target}), target)
            ptba.refresh_from_db()
            self.assertEqual(ptba.status, target)

    # --- B24 ---

    def test_b24_create_ptba_with_benefit_plan(self):
        error = self._mutation_error("createPtba", {
            "code": "UAT-B24", "name": "PTBA B24",
            "fiscalYearStart": "2026-01-01", "fiscalYearEnd": "2026-12-31",
            "benefitPlanId": str(self.benefit_plan.id),
        })
        self.assertIsNone(error)
        ptba = PTBA.objects.get(code="UAT-B24")
        self.assertEqual(ptba.benefit_plan_id, self.benefit_plan.id)
        self.assertEqual(ptba.status, PTBAStatus.DRAFT)

    def test_b24_update_ptba_sets_benefit_plan(self):
        ptba = self._ptba("UAT-B24U")
        error = self._mutation_error("updatePtba", {
            "id": str(ptba.id), "code": ptba.code, "name": ptba.name,
            "fiscalYearStart": "2026-01-01", "fiscalYearEnd": "2026-12-31",
            "benefitPlanId": str(self.benefit_plan.id),
        })
        self.assertIsNone(error)
        ptba.refresh_from_db()
        self.assertEqual(ptba.benefit_plan_id, self.benefit_plan.id)

    # --- B8 (backend side of the locked page) ---

    def test_b8_update_of_a_closed_ptba_is_refused(self):
        ptba = self._ptba("UAT-B8", status=PTBAStatus.CLOSED)
        self._mutation_error("updatePtba", {
            "id": str(ptba.id), "code": ptba.code, "name": "renamed after closing",
            "fiscalYearStart": "2026-01-01", "fiscalYearEnd": "2026-12-31",
        })
        ptba.refresh_from_db()
        self.assertEqual(ptba.name, "PTBA UAT-B8")


class UatSectionBClosedPtbaActivityTest(openIMISGraphQLTestCase):
    """B9: updateActivite on an activity of a CLOSED PTBA."""
    GRAPHQL_URL = f"/{settings.SITE_ROOT()}graphql"
    GRAPHQL_SCHEMA = True

    @classmethod
    def setUpTestData(cls):
        role = create_test_role(
            perm_names=['gql_activity_search_perms', 'gql_activity_update_perms'],
            name="UatSectionBClosedActivityRole",
        )
        cls.user = LogInHelper().get_or_create_user_api(username='uat_b9_act', roles=[role.id])
        cls.token = get_token(cls.user, BaseTestContext(user=cls.user))

    def test_b9_update_of_an_activity_of_a_closed_ptba_is_refused(self):
        from activity.models import Composante, SousComposante, Activite
        ptba = PTBA.objects.create(
            code="UAT-B9", name="PTBA UAT-B9", status=PTBAStatus.CLOSED,
            fiscal_year_start=datetime.date(2026, 1, 1), fiscal_year_end=datetime.date(2026, 12, 31),
            user_created=self.user, user_updated=self.user,
        )
        comp = Composante.objects.create(ptba=ptba, code="K1", name="K1")
        sc = SousComposante.objects.create(composante=comp, code="K1.1", name="K1.1")
        act = Activite.objects.create(sous_composante=sc, code="KA1", name="before closing")
        try:
            self.send_mutation("updateActivite", {"id": str(act.id), "name": "after closing"}, self.token)
        except ValueError:
            pass
        act.refresh_from_db()
        self.assertEqual(act.name, "before closing")
