import graphene


class StatusCountType(graphene.ObjectType):
    status = graphene.String()
    count = graphene.Int()


class FundingBreakdownType(graphene.ObjectType):
    source_code = graphene.String()
    source_name = graphene.String()
    amount = graphene.Decimal()
    percentage = graphene.Decimal()


class ComposantePerformanceType(graphene.ObjectType):
    composante_id = graphene.UUID()
    composante_code = graphene.String()
    composante_name = graphene.String()
    budget_prevu = graphene.Decimal()
    budget_engage = graphene.Decimal()
    budget_decaisse = graphene.Decimal()
    taux_engagement = graphene.Decimal()
    taux_decaissement = graphene.Decimal()
    taux_realisation = graphene.Decimal()


class QuarterlyTrendType(graphene.ObjectType):
    quarter = graphene.Int()
    taux_engagement = graphene.Decimal()
    taux_decaissement = graphene.Decimal()
    taux_realisation = graphene.Decimal()


class DelayedActivityType(graphene.ObjectType):
    activite_id = graphene.UUID()
    activite_name = graphene.String()
    composante_name = graphene.String()
    taux_realisation = graphene.Decimal()


class AlertType(graphene.ObjectType):
    activite_id = graphene.UUID()
    activite_name = graphene.String()
    message = graphene.String()
    severity = graphene.String()  # HIGH, MEDIUM


class PTBADashboardType(graphene.ObjectType):
    budget_prevu = graphene.Decimal()
    budget_engage = graphene.Decimal()
    budget_decaisse = graphene.Decimal()
    taux_engagement = graphene.Decimal()
    taux_decaissement = graphene.Decimal()
    taux_realisation = graphene.Decimal()
    activities_by_status = graphene.List(StatusCountType)
    funding_breakdown = graphene.List(FundingBreakdownType)
    composante_performance = graphene.List(ComposantePerformanceType)
    quarterly_trend = graphene.List(QuarterlyTrendType)
    top_delayed_activities = graphene.List(DelayedActivityType)
    alerts = graphene.List(AlertType)

    @staticmethod
    def _resolve_list(obj, key):
        raw = obj.get(key, []) if isinstance(obj, dict) else getattr(obj, key, [])
        return raw

    def resolve_activities_by_status(self, info):
        return [StatusCountType(**item) for item in self._resolve_list(self, 'activities_by_status')]

    def resolve_funding_breakdown(self, info):
        return [FundingBreakdownType(**item) for item in self._resolve_list(self, 'funding_breakdown')]

    def resolve_composante_performance(self, info):
        return [
            ComposantePerformanceType(**item)
            for item in self._resolve_list(self, 'composante_performance')
        ]

    def resolve_quarterly_trend(self, info):
        return [QuarterlyTrendType(**item) for item in self._resolve_list(self, 'quarterly_trend')]

    def resolve_top_delayed_activities(self, info):
        return [
            DelayedActivityType(**item)
            for item in self._resolve_list(self, 'top_delayed_activities')
        ]

    def resolve_alerts(self, info):
        return [AlertType(**item) for item in self._resolve_list(self, 'alerts')]
