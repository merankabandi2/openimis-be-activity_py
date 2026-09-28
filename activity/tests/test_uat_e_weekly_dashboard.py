"""
UAT section E (docs/metier/activites-uat.md): weekly planning entries and the
PTBA dashboard, exercised through the GraphQL schema so that permission
checks and the MutationLog error path run as in production.

Each test asserts the expected product behaviour of its UAT row.
"""
import base64
import datetime
import json
import uuid
from decimal import Decimal

from core.models import MutationLog, Role, RoleRight
from core.models.openimis_graphql_test_case import openIMISGraphQLTestCase, BaseTestContext
from core.test_helpers import create_test_interactive_user

from activity.models import (
    PTBA, Composante, SousComposante, Activite, ActivityStatus, SousActivite,
    FundingSource, SousActiviteFunding, QuarterlyExecution, WeeklyPlanEntry,
)

ALL_ACTIVITY_RIGHTS = list(range(802005, 802018))
MONDAY = datetime.date(2026, 7, 6)


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


def _relay_id(type_name, pk):
    return base64.b64encode(f"{type_name}:{pk}".encode()).decode()


class UatSectionEWeeklyTests(openIMISGraphQLTestCase):

    @classmethod
    def setUpTestData(cls):
        role = _role_with_rights("UAT E PTBA Gestion", ALL_ACTIVITY_RIGHTS)
        cls.user = create_test_interactive_user(username="uat_e_gest_test", roles=[role.id])
        cls.token = BaseTestContext(user=cls.user).get_jwt()

    def setUp(self):
        super().setUp()
        self.ptba = PTBA.objects.create(
            code="UAT-E-BE", name="UAT E backend",
            fiscal_year_start=datetime.date(2026, 7, 1),
            fiscal_year_end=datetime.date(2027, 6, 30),
        )
        comp = Composante.objects.create(ptba=self.ptba, code="1", name="C1")
        sc = SousComposante.objects.create(composante=comp, code="1.1", name="SC1.1")
        self.activite = Activite.objects.create(sous_composante=sc, code="1.1.1", name="Act")
        self.sa = SousActivite.objects.create(activite=self.activite, code="SA", name="Sous-activite E")

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

    def _create_args(self, week_start, sa_id=None, **extra):
        week_end = week_start + datetime.timedelta(days=4)
        args = (
            f'sousActiviteId: "{sa_id or self.sa.id}" weekStart: "{week_start.isoformat()}" '
            f'weekEnd: "{week_end.isoformat()}" '
        )
        for key, value in extra.items():
            args += f'{key}: "{value}" '
        return args

    # -- E2: entry created from a grid cell (payload of formatWeeklyPlanEntryGQL)

    def test_e2_create_weekly_entry(self):
        self._ok("createWeeklyPlanEntry", self._create_args(
            MONDAY, plannedDescription="Atelier", statusDescription="Salle reservee",
            status="PLANIFIE", responsible="UGP", intervenants="ONG"))
        entry = WeeklyPlanEntry.objects.get(sous_activite=self.sa, week_start=MONDAY)
        self.assertEqual(entry.week_end, datetime.date(2026, 7, 10))
        self.assertEqual(entry.planned_description, "Atelier")
        self.assertEqual(entry.status, "PLANIFIE")
        self.assertEqual(entry.responsible, "UGP")
        self.assertEqual(entry.intervenants, "ONG")

    def test_e2_create_with_relay_encoded_sous_activite_id_refused(self):
        # sousActiviteId is a UUID argument: a relay-encoded id is refused
        # before the mutation runs.
        encoded = _relay_id("SousActiviteGQLType", self.sa.id)
        content, _ = self._post("createWeeklyPlanEntry", self._create_args(MONDAY, sa_id=encoded))
        self.assertIn("errors", content)
        self.assertFalse(WeeklyPlanEntry.objects.filter(sous_activite=self.sa).exists())

    # -- E3: edit through the six statuses

    def test_e3_update_through_six_statuses(self):
        self._ok("createWeeklyPlanEntry", self._create_args(MONDAY, plannedDescription="Atelier"))
        entry = WeeklyPlanEntry.objects.get(sous_activite=self.sa, week_start=MONDAY)
        for status in ["EN_COURS", "REALISE", "REPORTE", "SUSPENDU", "PARTIELLEMENT_REALISE", "PLANIFIE"]:
            self._ok("updateWeeklyPlanEntry", f'id: "{entry.id}" status: "{status}"')
            entry.refresh_from_db()
            self.assertEqual(entry.status, status)

    def test_e3_update_imported_entry(self):
        # import_weekly_plan writes entries with update_or_create and no created_by.
        entry = WeeklyPlanEntry.objects.create(sous_activite=self.sa, week_start=MONDAY,
                                               week_end=MONDAY + datetime.timedelta(days=4))
        self.assertIsNone(entry.created_by_id)
        for status in ["EN_COURS", "REALISE", "REPORTE", "SUSPENDU", "PARTIELLEMENT_REALISE", "PLANIFIE"]:
            self._ok("updateWeeklyPlanEntry", f'id: "{entry.id}" status: "{status}"')
            entry.refresh_from_db()
            self.assertEqual(entry.status, status)

    def test_e3_unknown_status_refused(self):
        self._ok("createWeeklyPlanEntry", self._create_args(MONDAY))
        entry = WeeklyPlanEntry.objects.get(sous_activite=self.sa, week_start=MONDAY)
        self._failed("updateWeeklyPlanEntry", f'id: "{entry.id}" status: "INCONNU"')
        entry.refresh_from_db()
        self.assertEqual(entry.status, "PLANIFIE")

    # -- E4: delete

    def test_e4_delete_entry(self):
        entry = WeeklyPlanEntry.objects.create(sous_activite=self.sa, week_start=MONDAY,
                                               week_end=MONDAY + datetime.timedelta(days=4))
        self._ok("deleteWeeklyPlanEntry", f'ids: ["{entry.id}"]')
        self.assertFalse(WeeklyPlanEntry.objects.filter(id=entry.id).exists())

    # -- E5: non-Monday week start, duplicate week

    def test_e5_non_monday_week_start_refused_on_create(self):
        error = self._failed("createWeeklyPlanEntry", self._create_args(MONDAY + datetime.timedelta(days=1)))
        self.assertIn("Week start must be a Monday.", error)
        self.assertFalse(WeeklyPlanEntry.objects.filter(sous_activite=self.sa).exists())

    def test_e5_non_monday_week_start_refused_on_update(self):
        self._ok("createWeeklyPlanEntry", self._create_args(MONDAY))
        entry = WeeklyPlanEntry.objects.get(sous_activite=self.sa, week_start=MONDAY)
        error = self._failed("updateWeeklyPlanEntry", f'id: "{entry.id}" weekStart: "2026-07-08"')
        self.assertIn("Week start must be a Monday.", error)
        self.assertNotIn("created_by", error)
        entry.refresh_from_db()
        self.assertEqual(entry.week_start, MONDAY)

    def test_e5_duplicate_week_refused(self):
        self._ok("createWeeklyPlanEntry", self._create_args(MONDAY, plannedDescription="Premiere"))
        error = self._failed("createWeeklyPlanEntry", self._create_args(MONDAY, plannedDescription="Seconde"))
        print(f"\nE5 duplicate error: {error}")
        self.assertIn("already exists", error)
        self.assertEqual(WeeklyPlanEntry.objects.filter(sous_activite=self.sa, week_start=MONDAY).count(), 1)


class UatSectionEDashboardTests(openIMISGraphQLTestCase):

    QUERY = """
    query {{ ptbaDashboard(ptbaId: "{ptba_id}" {extra}) {{
      budgetPrevu budgetEngage budgetDecaisse tauxEngagement tauxDecaissement tauxRealisation
      activitiesByStatus {{ status count }}
      fundingBreakdown {{ sourceCode sourceName amount percentage }}
      composantePerformance {{ composanteCode budgetPrevu budgetDecaisse tauxDecaissement tauxRealisation }}
      quarterlyTrend {{ quarter tauxEngagement tauxDecaissement tauxRealisation }}
      topDelayedActivities {{ activiteName composanteName tauxRealisation }}
      alerts {{ activiteName message severity }}
    }} }}
    """

    @classmethod
    def setUpTestData(cls):
        role = _role_with_rights("UAT E PTBA Tableau", ALL_ACTIVITY_RIGHTS)
        cls.user = create_test_interactive_user(username="uat_e_dash_test", roles=[role.id])
        cls.token = BaseTestContext(user=cls.user).get_jwt()

    def setUp(self):
        super().setUp()
        self.ptba = PTBA.objects.create(
            code="UAT-E-DASH", name="UAT E dashboard",
            fiscal_year_start=datetime.date(2025, 7, 1),
            fiscal_year_end=datetime.date(2026, 6, 30),
        )
        self.comp = Composante.objects.create(ptba=self.ptba, code="1", name="Composante E")
        self.sc = SousComposante.objects.create(composante=self.comp, code="1.1", name="SC")

    def _dashboard(self, extra=""):
        response = self.query(
            self.QUERY.format(ptba_id=self.ptba.id, extra=extra),
            headers={"HTTP_AUTHORIZATION": f"Bearer {self.token}"},
        )
        content = json.loads(response.content)
        self.assertNotIn("errors", content, content)
        return content["data"]["ptbaDashboard"]

    def _activite(self, code, status):
        return Activite.objects.create(sous_composante=self.sc, code=code, name=f"Activite {code}", status=status)

    def _sa(self, activite, code):
        return SousActivite.objects.create(
            activite=activite, code=code, name=f"SA {code}",
            quantity_t1=Decimal("10"), quantity_total=Decimal("10"),
            unit_cost=Decimal("1000"), budget_t1=Decimal("10000"), budget_total=Decimal("10000"),
        )

    def _execution(self, sa, quarter, year, prevu, engage, decaisse, attendus, realises):
        # No indicator is linked, so the post_save indicator feed writes nothing.
        return QuarterlyExecution.objects.create(
            sous_activite=sa, quarter=quarter, year=year,
            budget_prevu=Decimal(prevu), budget_engage=Decimal(engage), budget_decaisse=Decimal(decaisse),
            resultats_attendus=Decimal(attendus), resultats_realises=Decimal(realises),
        )

    # -- E11: PTBA without executions

    def test_e11_ptba_without_execution_returns_zeros(self):
        self._sa(self._activite("A1", ActivityStatus.PLANIFIE), "S1")
        data = self._dashboard()
        for key in ("budgetPrevu", "budgetEngage", "budgetDecaisse",
                    "tauxEngagement", "tauxDecaissement", "tauxRealisation"):
            self.assertEqual(Decimal(str(data[key])), Decimal("0"), key)
        self.assertEqual(data["alerts"], [])
        self.assertEqual(len(data["quarterlyTrend"]), 4)

    # -- E12: KPIs, funding breakdown, alerts

    def test_e12_kpis_funding_alerts(self):
        high = self._activite("H", ActivityStatus.EN_COURS)
        medium = self._activite("M", ActivityStatus.EN_COURS)
        empty = self._activite("Z", ActivityStatus.EN_COURS)
        ok = self._activite("K", ActivityStatus.EN_COURS)
        sa_h, sa_m, sa_z, sa_k = (self._sa(a, a.code) for a in (high, medium, empty, ok))
        self._execution(sa_h, 1, 2026, "10000", "5000", "2000", "10", "2")    # 20 %
        self._execution(sa_m, 1, 2026, "10000", "5000", "2000", "10", "4")    # 40 %
        self._execution(sa_k, 1, 2026, "10000", "5000", "2000", "10", "8")    # 80 %
        bm = FundingSource.objects.create(code="UAE-BM", name="Banque")
        gov = FundingSource.objects.create(code="UAE-GOV", name="Etat")
        SousActiviteFunding.objects.create(sous_activite=sa_h, funding_source=bm, amount=Decimal("7500"))
        SousActiviteFunding.objects.create(sous_activite=sa_m, funding_source=gov, amount=Decimal("2500"))

        data = self._dashboard()
        self.assertEqual(Decimal(str(data["budgetPrevu"])), Decimal("30000"))
        self.assertEqual(Decimal(str(data["budgetEngage"])), Decimal("15000"))
        self.assertEqual(Decimal(str(data["budgetDecaisse"])), Decimal("6000"))
        self.assertAlmostEqual(float(data["tauxEngagement"]), 50.0, places=2)
        self.assertAlmostEqual(float(data["tauxDecaissement"]), 20.0, places=2)
        self.assertAlmostEqual(float(data["tauxRealisation"]), 14 / 30 * 100, places=2)

        funding = {f["sourceCode"]: f for f in data["fundingBreakdown"]}
        self.assertAlmostEqual(float(funding["UAE-BM"]["percentage"]), 75.0, places=2)
        self.assertAlmostEqual(float(funding["UAE-GOV"]["percentage"]), 25.0, places=2)

        severities = {a["activiteName"]: a["severity"] for a in data["alerts"]}
        self.assertEqual(severities, {
            "Activite H": "HIGH", "Activite M": "MEDIUM", "Activite Z": "MEDIUM",
        })
        self.assertEqual(data["topDelayedActivities"][0]["activiteName"], "Activite Z")
        statuses = {s["status"]: s["count"] for s in data["activitiesByStatus"]}
        self.assertEqual(statuses, {"EN_COURS": 4})

    # -- E13: quarter filter; no year filter on screen

    def test_e13_quarter_filter_merges_years(self):
        sa = self._sa(self._activite("Y", ActivityStatus.EN_COURS), "SY")
        self._execution(sa, 1, 2025, "10000", "1000", "0", "10", "1")
        self._execution(sa, 1, 2026, "10000", "3000", "0", "10", "3")
        self._execution(sa, 2, 2026, "10000", "9000", "0", "10", "9")
        q1 = self._dashboard("quarter: 1")
        # The screen sends no year: T1 of both years is summed.
        self.assertEqual(Decimal(str(q1["budgetPrevu"])), Decimal("20000"))
        self.assertEqual(Decimal(str(q1["budgetEngage"])), Decimal("4000"))
        all_quarters = self._dashboard()
        self.assertEqual(Decimal(str(all_quarters["budgetPrevu"])), Decimal("30000"))
        q1_2026 = self._dashboard("quarter: 1 year: 2026")
        self.assertEqual(Decimal(str(q1_2026["budgetEngage"])), Decimal("3000"))
