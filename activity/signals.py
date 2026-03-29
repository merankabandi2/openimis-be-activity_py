"""
Signals for Activity module.

M&E indicator auto-feeding from quarterly execution reports.
When a QuarterlyExecution is saved, linked M&E indicators are automatically updated.
"""
import datetime
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from activity.models import QuarterlyExecution

logger = logging.getLogger(__name__)


def _quarter_end_date(quarter, year):
    """Return the last day of the quarter."""
    month = quarter * 3
    # Get first day of next month, then subtract one day
    if month == 12:
        return datetime.date(year, 12, 31)
    next_month_first = datetime.date(year, month + 1, 1)
    return next_month_first - datetime.timedelta(days=1)


@receiver(post_save, sender=QuarterlyExecution)
def feed_indicators(sender, instance, **kwargs):
    """Auto-feed M&E indicator achievements from quarterly execution."""
    activite = instance.sous_activite.activite

    if not hasattr(activite, 'indicators'):
        return

    try:
        from merankabandi.models import IndicatorAchievement
    except ImportError:
        return

    indicators = activite.indicators.all()
    if not indicators.exists():
        return

    quarter_end = _quarter_end_date(instance.quarter, instance.year)

    for indicator in indicators:
        IndicatorAchievement.objects.update_or_create(
            indicator=indicator,
            date=quarter_end,
            defaults={
                'achieved': instance.resultats_realises,
                'comment': f"Auto: {activite.code} T{instance.quarter} {instance.year}",
            },
        )
        logger.info(
            "Auto-fed indicator %s from execution %s T%s %s (achieved=%s)",
            indicator.id, activite.code, instance.quarter, instance.year,
            instance.resultats_realises,
        )
