import logging
from decimal import Decimal
from django.db.models import Sum, Count, Q, F
from django.db.models.functions import Coalesce

from activity.models import (
    PTBA, Composante, Activite, ActivityStatus,
    SousActiviteFunding, QuarterlyExecution,
)

logger = logging.getLogger(__name__)

ZERO = Decimal('0')


def _safe_rate(numerator, denominator):
    """Compute percentage rate, returning 0 if denominator is zero."""
    if not denominator:
        return ZERO
    return (numerator / denominator) * 100


class PTBADashboardService:
    """Aggregation service for PTBA dashboard KPIs."""

    @classmethod
    def get_overview(cls, ptba_id, quarter=None, year=None):
        """
        Top-level KPIs for a PTBA.

        Returns a dict with:
        - budget_prevu, budget_engage, budget_decaisse
        - resultats_attendus, resultats_realises
        - taux_engagement, taux_decaissement, taux_realisation
        - activities_by_status
        - funding_breakdown
        - composante_performance
        - quarterly_trend
        - top_delayed_activities
        - alerts
        """
        ptba = PTBA.objects.get(id=ptba_id)

        # Build execution queryset scoped to this PTBA
        exec_qs = QuarterlyExecution.objects.filter(
            sous_activite__activite__sous_composante__composante__ptba=ptba,
        )
        if quarter is not None:
            exec_qs = exec_qs.filter(quarter=quarter)
        if year is not None:
            exec_qs = exec_qs.filter(year=year)

        # Aggregate totals
        totals = exec_qs.aggregate(
            budget_prevu=Coalesce(Sum('budget_prevu'), ZERO),
            budget_engage=Coalesce(Sum('budget_engage'), ZERO),
            budget_decaisse=Coalesce(Sum('budget_decaisse'), ZERO),
            resultats_attendus=Coalesce(Sum('resultats_attendus'), ZERO),
            resultats_realises=Coalesce(Sum('resultats_realises'), ZERO),
        )

        budget_prevu = totals['budget_prevu']
        budget_engage = totals['budget_engage']
        budget_decaisse = totals['budget_decaisse']
        resultats_attendus = totals['resultats_attendus']
        resultats_realises = totals['resultats_realises']

        taux_engagement = _safe_rate(budget_engage, budget_prevu)
        taux_decaissement = _safe_rate(budget_decaisse, budget_prevu)
        taux_realisation = _safe_rate(resultats_realises, resultats_attendus)

        # Activities by status
        activite_qs = Activite.objects.filter(
            sous_composante__composante__ptba=ptba,
        )
        activities_by_status = list(
            activite_qs.values('status').annotate(count=Count('id')).order_by('status')
        )

        # Funding breakdown
        funding_qs = SousActiviteFunding.objects.filter(
            sous_activite__activite__sous_composante__composante__ptba=ptba,
        )
        funding_agg = list(
            funding_qs.values(
                source_code=F('funding_source__code'),
                source_name=F('funding_source__name'),
            ).annotate(
                amount=Coalesce(Sum('amount'), ZERO),
            ).order_by('-amount')
        )
        funding_total = sum(item['amount'] for item in funding_agg)
        funding_breakdown = []
        for item in funding_agg:
            funding_breakdown.append({
                'source_code': item['source_code'],
                'source_name': item['source_name'],
                'amount': item['amount'],
                'percentage': _safe_rate(item['amount'], funding_total),
            })

        # Composante performance
        composante_performance = cls._get_composante_performance(ptba, quarter, year)

        # Quarterly trend (T1-T4)
        quarterly_trend = cls._get_quarterly_trend(ptba, year)

        # Top 10 delayed activities
        top_delayed = cls._get_top_delayed(ptba, quarter, year)

        # Alerts: EN_COURS activities with <50% realisation
        alerts = cls._get_alerts(ptba, quarter, year)

        return {
            'budget_prevu': budget_prevu,
            'budget_engage': budget_engage,
            'budget_decaisse': budget_decaisse,
            'taux_engagement': taux_engagement,
            'taux_decaissement': taux_decaissement,
            'taux_realisation': taux_realisation,
            'activities_by_status': activities_by_status,
            'funding_breakdown': funding_breakdown,
            'composante_performance': composante_performance,
            'quarterly_trend': quarterly_trend,
            'top_delayed_activities': top_delayed,
            'alerts': alerts,
        }

    @classmethod
    def get_composante_summary(cls, composante_id, quarter=None, year=None):
        """Per-composante breakdown."""
        composante = Composante.objects.get(id=composante_id)

        exec_qs = QuarterlyExecution.objects.filter(
            sous_activite__activite__sous_composante__composante=composante,
        )
        if quarter is not None:
            exec_qs = exec_qs.filter(quarter=quarter)
        if year is not None:
            exec_qs = exec_qs.filter(year=year)

        totals = exec_qs.aggregate(
            budget_prevu=Coalesce(Sum('budget_prevu'), ZERO),
            budget_engage=Coalesce(Sum('budget_engage'), ZERO),
            budget_decaisse=Coalesce(Sum('budget_decaisse'), ZERO),
            resultats_attendus=Coalesce(Sum('resultats_attendus'), ZERO),
            resultats_realises=Coalesce(Sum('resultats_realises'), ZERO),
        )

        budget_prevu = totals['budget_prevu']
        budget_decaisse = totals['budget_decaisse']
        resultats_attendus = totals['resultats_attendus']
        resultats_realises = totals['resultats_realises']

        return {
            'composante_id': composante.id,
            'composante_code': composante.code,
            'composante_name': composante.name,
            'budget_prevu': budget_prevu,
            'budget_decaisse': budget_decaisse,
            'taux_decaissement': _safe_rate(budget_decaisse, budget_prevu),
            'taux_realisation': _safe_rate(resultats_realises, resultats_attendus),
        }

    @classmethod
    def _get_composante_performance(cls, ptba, quarter=None, year=None):
        """Aggregate execution rates per composante in a single query."""
        exec_qs = QuarterlyExecution.objects.filter(
            sous_activite__activite__sous_composante__composante__ptba=ptba,
        )
        if quarter is not None:
            exec_qs = exec_qs.filter(quarter=quarter)
        if year is not None:
            exec_qs = exec_qs.filter(year=year)

        composante_aggs = exec_qs.values(
            'sous_activite__activite__sous_composante__composante__id',
            'sous_activite__activite__sous_composante__composante__code',
            'sous_activite__activite__sous_composante__composante__name',
        ).annotate(
            budget_prevu=Coalesce(Sum('budget_prevu'), ZERO),
            budget_engage=Coalesce(Sum('budget_engage'), ZERO),
            budget_decaisse=Coalesce(Sum('budget_decaisse'), ZERO),
            resultats_attendus=Coalesce(Sum('resultats_attendus'), ZERO),
            resultats_realises=Coalesce(Sum('resultats_realises'), ZERO),
        ).order_by(
            'sous_activite__activite__sous_composante__composante__sort_order',
            'sous_activite__activite__sous_composante__composante__code',
        )

        results = []
        for row in composante_aggs:
            bp = row['budget_prevu']
            be = row['budget_engage']
            bd = row['budget_decaisse']
            ra = row['resultats_attendus']
            rr = row['resultats_realises']
            results.append({
                'composante_id': row['sous_activite__activite__sous_composante__composante__id'],
                'composante_code': row['sous_activite__activite__sous_composante__composante__code'],
                'composante_name': row['sous_activite__activite__sous_composante__composante__name'],
                'budget_prevu': bp,
                'budget_engage': be,
                'budget_decaisse': bd,
                'taux_engagement': _safe_rate(be, bp),
                'taux_decaissement': _safe_rate(bd, bp),
                'taux_realisation': _safe_rate(rr, ra),
            })
        return results

    @classmethod
    def _get_quarterly_trend(cls, ptba, year=None):
        """T1-T4 execution rates for the PTBA."""
        results = []
        for q in range(1, 5):
            exec_qs = QuarterlyExecution.objects.filter(
                sous_activite__activite__sous_composante__composante__ptba=ptba,
                quarter=q,
            )
            if year is not None:
                exec_qs = exec_qs.filter(year=year)

            totals = exec_qs.aggregate(
                budget_prevu=Coalesce(Sum('budget_prevu'), ZERO),
                budget_engage=Coalesce(Sum('budget_engage'), ZERO),
                budget_decaisse=Coalesce(Sum('budget_decaisse'), ZERO),
                resultats_attendus=Coalesce(Sum('resultats_attendus'), ZERO),
                resultats_realises=Coalesce(Sum('resultats_realises'), ZERO),
            )
            bp = totals['budget_prevu']
            be = totals['budget_engage']
            bd = totals['budget_decaisse']
            ra = totals['resultats_attendus']
            rr = totals['resultats_realises']

            results.append({
                'quarter': q,
                'taux_engagement': _safe_rate(be, bp),
                'taux_decaissement': _safe_rate(bd, bp),
                'taux_realisation': _safe_rate(rr, ra),
            })
        return results

    @classmethod
    def _get_activity_execution_aggregates(cls, ptba, quarter=None, year=None):
        """Single-query aggregate of execution data per EN_COURS activity."""
        exec_filter = Q(
            sous_activites__executions__sous_activite__activite__sous_composante__composante__ptba=ptba,
        )
        if quarter is not None:
            exec_filter &= Q(sous_activites__executions__quarter=quarter)
        if year is not None:
            exec_filter &= Q(sous_activites__executions__year=year)

        return Activite.objects.filter(
            sous_composante__composante__ptba=ptba,
            status=ActivityStatus.EN_COURS,
        ).select_related(
            'sous_composante__composante',
        ).annotate(
            total_attendus=Coalesce(
                Sum('sous_activites__executions__resultats_attendus', filter=exec_filter), ZERO
            ),
            total_realises=Coalesce(
                Sum('sous_activites__executions__resultats_realises', filter=exec_filter), ZERO
            ),
        )

    @classmethod
    def _get_top_delayed(cls, ptba, quarter=None, year=None):
        """Top 10 activities with lowest taux_realisation."""
        activities = cls._get_activity_execution_aggregates(ptba, quarter, year)
        results = []
        for act in activities:
            taux = _safe_rate(act.total_realises, act.total_attendus)
            results.append({
                'activite_id': act.id,
                'activite_name': act.name,
                'composante_name': act.sous_composante.composante.name,
                'taux_realisation': taux,
            })
        results.sort(key=lambda x: x['taux_realisation'])
        return results[:10]

    @classmethod
    def _get_alerts(cls, ptba, quarter=None, year=None):
        """EN_COURS activities with <50% realisation."""
        activities = cls._get_activity_execution_aggregates(ptba, quarter, year)
        alerts = []
        for act in activities:
            if act.total_attendus == ZERO:
                alerts.append({
                    'activite_id': act.id,
                    'activite_name': act.name,
                    'message': f"Aucun resultat attendu enregistre pour {act.code}",
                    'severity': 'MEDIUM',
                })
                continue
            taux = _safe_rate(act.total_realises, act.total_attendus)
            if taux < Decimal('25'):
                alerts.append({
                    'activite_id': act.id,
                    'activite_name': act.name,
                    'message': f"Taux de realisation critique: {taux:.1f}% pour {act.code}",
                    'severity': 'HIGH',
                })
            elif taux < Decimal('50'):
                alerts.append({
                    'activite_id': act.id,
                    'activite_name': act.name,
                    'message': f"Taux de realisation faible: {taux:.1f}% pour {act.code}",
                    'severity': 'MEDIUM',
                })
        return alerts
