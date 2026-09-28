"""UAT row A19 (docs/metier/activites-uat.md): list queries read by an
authenticated account that holds no activity right (802005-802017)."""
import importlib

from django.conf import settings
from django.test import RequestFactory, TestCase

from core.test_helpers import LogInHelper, create_test_role
from activity.models import (
    PTBA, Composante, SousComposante, Activite, SousActivite,
    QuarterlyExecution, WeeklyPlanEntry,
)

ACTIVITY_RIGHTS = set(range(802005, 802018))


def _schema():
    module, attr = settings.GRAPHENE["SCHEMA"].rsplit(".", 1)
    return getattr(importlib.import_module(module), attr)


class ListQueriesWithoutModuleRightTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        role = create_test_role(perm_names=["gql_indicator_search_perms"], name="UatA19NoActivityRole")
        cls.user = LogInHelper().get_or_create_user_api(username="uat_a19", roles=[role.id])
        cls.ptba = PTBA.objects.create(
            code="UAT-A19", name="A19", fiscal_year_start="2026-01-01", fiscal_year_end="2026-12-31",
            user_created=cls.user, user_updated=cls.user,
        )
        comp = Composante.objects.create(ptba=cls.ptba, code="1", name="C")
        sc = SousComposante.objects.create(composante=comp, code="1.1", name="SC")
        act = Activite.objects.create(sous_composante=sc, code="A1", name="Act")
        cls.sa = SousActivite.objects.create(
            activite=act, name="SA", unit="u", budget_total=100, budget_t1=100, unit_cost=10, quantity_total=10,
        )
        QuarterlyExecution.objects.create(
            sous_activite=cls.sa, quarter=1, year=2026, budget_prevu=100, budget_engage=10,
            budget_decaisse=5, resultats_attendus=10, resultats_realises=1,
        )
        WeeklyPlanEntry.objects.create(
            sous_activite=cls.sa, week_start="2026-01-05", week_end="2026-01-09", planned_description="x",
        )

    def _execute(self, query):
        request = RequestFactory().post("/api/graphql")
        request.user = self.user
        return _schema().execute(query, context_value=request)

    def test_account_holds_no_activity_right(self):
        self.assertFalse(set(self.user.rights or []) & ACTIVITY_RIGHTS)

    def test_list_queries_refused_without_activity_right(self):
        for field in ("ptba", "activite", "sousActivite", "quarterlyExecution", "weeklyPlanEntry"):
            with self.subTest(field=field):
                result = self._execute("{ %s { totalCount } }" % field)
                self.assertEqual([str(e) for e in result.errors or []],
                                 ["activity.query.insufficient_rights"], field)
                self.assertIsNone(result.data[field], field)
