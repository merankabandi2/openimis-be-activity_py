import graphene
from graphene_django import DjangoObjectType

from core import ExtendedConnection
from activity.models import (
    PTBA, Composante, SousComposante, Activite, SousActivite,
    FundingSource, SousActiviteFunding, QuarterlyExecution,
    ActivityStatusTransition, WeeklyPlanEntry,
)


class PTBAGQLType(DjangoObjectType):
    uuid = graphene.String(source='id')

    class Meta:
        model = PTBA
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "code": ["exact", "icontains"],
            "name": ["exact", "icontains"],
            "status": ["exact", "in"],
            "fiscal_year_start": ["exact", "gte", "lte"],
            "fiscal_year_end": ["exact", "gte", "lte"],
            "benefit_plan": ["exact", "isnull"],
        }
        connection_class = ExtendedConnection


class ComposanteGQLType(DjangoObjectType):
    uuid = graphene.String(source='id')

    class Meta:
        model = Composante
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "ptba__id": ["exact"],
            "code": ["exact", "icontains"],
            "name": ["exact", "icontains"],
        }
        connection_class = ExtendedConnection


class SousComposanteGQLType(DjangoObjectType):
    uuid = graphene.String(source='id')

    class Meta:
        model = SousComposante
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "composante__id": ["exact"],
            "composante__ptba__id": ["exact"],
            "code": ["exact", "icontains"],
            "name": ["exact", "icontains"],
        }
        connection_class = ExtendedConnection


class ActiviteGQLType(DjangoObjectType):
    uuid = graphene.String(source='id')
    budget_total = graphene.Decimal()

    @classmethod
    def get_queryset(cls, queryset, info):
        # Annotate once per connection instead of one aggregate per row.
        from django.db.models import DecimalField, Sum, Value
        from django.db.models.functions import Coalesce
        return queryset.annotate(budget_total_agg=Coalesce(
            Sum('sous_activites__budget_total'),
            Value(0, output_field=DecimalField(max_digits=18, decimal_places=2)),
        ))

    def resolve_budget_total(self, info):
        total = getattr(self, 'budget_total_agg', None)
        if total is None:
            # Instance not obtained through the annotated connection queryset
            # (e.g. nested access) — fall back to the per-instance aggregate.
            from django.db.models import Sum
            total = SousActivite.objects.filter(activite=self).aggregate(
                total=Sum('budget_total')
            )['total']
        return total or 0

    class Meta:
        model = Activite
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "sous_composante__id": ["exact"],
            "sous_composante__composante__id": ["exact"],
            "sous_composante__composante__ptba__id": ["exact"],
            "code": ["exact", "icontains"],
            "name": ["exact", "icontains"],
            "status": ["exact", "in"],
            "implementing_structure": ["exact", "icontains"],
            "province": ["exact", "icontains"],
            "revision_status": ["exact", "in"],
        }
        connection_class = ExtendedConnection


class SousActiviteGQLType(DjangoObjectType):
    uuid = graphene.String(source='id')

    class Meta:
        model = SousActivite
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "activite__id": ["exact"],
            "activite__sous_composante__id": ["exact"],
            "activite__sous_composante__composante__id": ["exact"],
            "activite__sous_composante__composante__ptba__id": ["exact"],
            "code": ["exact", "icontains"],
            "name": ["exact", "icontains"],
            "expense_category_code": ["exact"],
            "revision_status": ["exact", "in"],
            "responsible": ["exact", "icontains"],
        }
        connection_class = ExtendedConnection


class FundingSourceGQLType(DjangoObjectType):
    uuid = graphene.String(source='id')

    class Meta:
        model = FundingSource
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "code": ["exact", "icontains"],
            "name": ["exact", "icontains"],
            "is_active": ["exact"],
        }
        connection_class = ExtendedConnection


class SousActiviteFundingGQLType(DjangoObjectType):
    uuid = graphene.String(source='id')

    class Meta:
        model = SousActiviteFunding
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "sous_activite__id": ["exact"],
            "funding_source__id": ["exact"],
            "funding_source__code": ["exact"],
        }
        connection_class = ExtendedConnection


class QuarterlyExecutionGQLType(DjangoObjectType):
    uuid = graphene.String(source='id')

    class Meta:
        model = QuarterlyExecution
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "sous_activite__id": ["exact"],
            "sous_activite__activite__id": ["exact"],
            "quarter": ["exact"],
            "year": ["exact"],
        }
        connection_class = ExtendedConnection


class ActivityStatusTransitionGQLType(DjangoObjectType):
    uuid = graphene.String(source='id')

    class Meta:
        model = ActivityStatusTransition
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "activite__id": ["exact"],
            "from_status": ["exact"],
            "to_status": ["exact"],
        }
        connection_class = ExtendedConnection


class WeeklyPlanEntryGQLType(DjangoObjectType):
    uuid = graphene.String(source='id')

    class Meta:
        model = WeeklyPlanEntry
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            "id": ["exact"],
            "sous_activite__id": ["exact"],
            "sous_activite__activite__id": ["exact"],
            "week_start": ["exact", "gte", "lte"],
            "status": ["exact", "in"],
            "responsible": ["exact", "icontains"],
        }
        connection_class = ExtendedConnection
