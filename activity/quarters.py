"""Quarterly (T1-T4) split of a sous-activite's quantity and budget."""
from decimal import Decimal

CENT = Decimal('0.01')
QUARTERLY_QUANTITY_FIELDS = ('quantity_t1', 'quantity_t2', 'quantity_t3', 'quantity_t4')
QUARTERLY_BUDGET_FIELDS = ('budget_t1', 'budget_t2', 'budget_t3', 'budget_t4')


def split_by_quarter(total, weights):
    """Split `total` over T1-T4 in proportion to `weights`, evenly when the
    weights sum to 0. Parts are rounded to the cent and the quarter with the
    largest weight takes the rounding remainder, so the parts sum to `total`.
    """
    total = Decimal(total or 0)
    weights = [Decimal(w or 0) for w in weights]
    if sum(weights) <= 0:
        weights = [Decimal('1')] * 4
    weight_sum = sum(weights)
    parts = [(total * w / weight_sum).quantize(CENT) for w in weights]
    largest = max(range(4), key=lambda i: weights[i])
    parts[largest] += total - sum(parts)
    return parts


def quarterly_split(shape, quantity_total, budget_total):
    """T1-T4 quantity and budget fields for the given totals.

    `shape` is a sous-activite whose current split is kept (by budget, else by
    quantity); with no shape, or an empty one, the totals are split evenly.
    """
    weights = [0, 0, 0, 0]
    if shape is not None:
        weights = [getattr(shape, f) for f in QUARTERLY_BUDGET_FIELDS]
        if sum(weights) <= 0:
            weights = [getattr(shape, f) for f in QUARTERLY_QUANTITY_FIELDS]
    return {
        **dict(zip(QUARTERLY_QUANTITY_FIELDS, split_by_quarter(quantity_total, weights))),
        **dict(zip(QUARTERLY_BUDGET_FIELDS, split_by_quarter(budget_total, weights))),
    }
