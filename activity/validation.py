"""
Validation rules for the Activity module.

Budget validation and transition rule enforcement.
"""
from activity.models import ActivityStatus


def validate_budget_consistency(sous_activite):
    """Validate that quarterly budgets sum to the total budget."""
    quarterly_sum = (
        sous_activite.budget_t1
        + sous_activite.budget_t2
        + sous_activite.budget_t3
        + sous_activite.budget_t4
    )
    if quarterly_sum != sous_activite.budget_total:
        return (
            f"Quarterly budgets ({quarterly_sum}) do not sum to total "
            f"({sous_activite.budget_total}) for {sous_activite.code}"
        )
    return None


def validate_funding_allocation(sous_activite):
    """Validate that funding allocations do not exceed the budget total."""
    total_funding = sum(
        alloc.amount for alloc in sous_activite.funding_allocations.all()
    )
    if total_funding > sous_activite.budget_total:
        return (
            f"Total funding ({total_funding}) exceeds budget total "
            f"({sous_activite.budget_total}) for {sous_activite.code}"
        )
    return None


def validate_transition_preconditions(activite, to_status):
    """
    Validate preconditions for a status transition.

    Returns a list of error messages (empty if valid).
    """
    errors = []

    if to_status == ActivityStatus.BUDGETISE:
        # Must have at least one sous-activite with budget
        sous_activites = activite.sous_activites.all()
        if not sous_activites.exists():
            errors.append("Activity must have at least one sous-activite to be budgetised.")
        total_budget = sum(sa.budget_total for sa in sous_activites)
        if total_budget <= 0:
            errors.append("Activity must have a positive budget to be budgetised.")

    if to_status == ActivityStatus.CLOTURE:
        # All sous-activites should have at least some execution data
        sous_activites = activite.sous_activites.all()
        for sa in sous_activites:
            if not sa.executions.exists():
                errors.append(
                    f"Sous-activite {sa.code} has no execution data. "
                    f"Consider reporting before closing."
                )

    return errors
