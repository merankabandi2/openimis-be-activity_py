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


def ptba_quarter_end(ptba, quarter):
    """Last day of quarter 1 to 4 of the PTBA. The PTBA's quarters are those
    of its own year: T1 starts in the month of fiscal_year_start (July for a
    July-June PTBA, so T1 = July to September)."""
    start = ptba.fiscal_year_start
    months = start.month - 1 + 3 * quarter
    next_quarter_start = datetime.date(start.year + months // 12, months % 12 + 1, 1)
    return next_quarter_start - datetime.timedelta(days=1)


AUTO_COMMENT_PREFIX = "Auto:"


@receiver(post_save, sender=QuarterlyExecution)
def feed_indicators(sender, instance, **kwargs):
    """Auto-feed M&E indicator achievements from quarterly execution.

    The achievement of an indicator for a quarter is the sum of
    `resultats_realises` over every execution of that quarter whose activity
    is linked to the indicator. It is dated the last day of that quarter of the
    activity's PTBA (ptba_quarter_end) and written to the row this signal owns,
    found by its comment (AUTO_COMMENT_PREFIX, quarter and year); manual
    achievements are left untouched.
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

    quarter_end = ptba_quarter_end(activite.sous_composante.composante.ptba, instance.quarter)
    comment = f"{AUTO_COMMENT_PREFIX} T{instance.quarter} {instance.year}"

    for indicator in indicators:
        achieved = QuarterlyExecution.objects.filter(
            quarter=instance.quarter,
            year=instance.year,
            sous_activite__activite__indicators=indicator,
        ).aggregate(total=Sum('resultats_realises'))['total'] or Decimal('0')
        auto_row = IndicatorAchievement.objects.filter(
            indicator=indicator,
            comment=comment,
        ).order_by('id').first()
        if auto_row:
            auto_row.achieved = achieved
            auto_row.date = quarter_end
            auto_row.save(update_fields=['achieved', 'date'])
        else:
            IndicatorAchievement.objects.create(
                indicator=indicator, date=quarter_end, achieved=achieved, comment=comment,
            )
        logger.info(
            "Auto-fed indicator %s for T%s %s (achieved=%s)",
            indicator.id, instance.quarter, instance.year, achieved,
        )
