"""
Signals for Activity module.

M&E indicator auto-feeding from quarterly execution reports.
When a QuarterlyExecution is saved, linked M&E indicators are automatically updated.
"""
import datetime
import logging
from decimal import Decimal

from django.db.models import Sum
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


AUTO_COMMENT_PREFIX = "Auto:"


@receiver(post_save, sender=QuarterlyExecution)
def feed_indicators(sender, instance, **kwargs):
    """Auto-feed M&E indicator achievements from quarterly execution.

    The achievement of an indicator for a quarter is the sum of
    `resultats_realises` over every execution of that quarter whose activity
    is linked to the indicator. It is written to the row this signal owns
    (comment starting with AUTO_COMMENT_PREFIX); manual achievements on the
    same date are left untouched.
    """
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
    comment = f"{AUTO_COMMENT_PREFIX} T{instance.quarter} {instance.year}"

    for indicator in indicators:
        achieved = QuarterlyExecution.objects.filter(
            quarter=instance.quarter,
            year=instance.year,
            sous_activite__activite__indicators=indicator,
        ).aggregate(total=Sum('resultats_realises'))['total'] or Decimal('0')
        auto_row = IndicatorAchievement.objects.filter(
            indicator=indicator,
            date=quarter_end,
            comment__startswith=AUTO_COMMENT_PREFIX,
        ).order_by('id').first()
        if auto_row:
            auto_row.achieved = achieved
            auto_row.comment = comment
            auto_row.save(update_fields=['achieved', 'comment'])
        else:
            IndicatorAchievement.objects.create(
                indicator=indicator, date=quarter_end, achieved=achieved, comment=comment,
            )
        logger.info(
            "Auto-fed indicator %s for T%s %s (achieved=%s)",
            indicator.id, instance.quarter, instance.year, achieved,
        )
