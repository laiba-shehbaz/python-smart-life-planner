"""Classifies a plan against the available budget."""
from collections import namedtuple

from utils.calculations import format_pkr
from utils.validators import ValidationError

FeasibilityResult = namedtuple(
    "FeasibilityResult",
    "status budget total difference remaining shortage is_feasible emergency_is_deciding",
)


class TripFeasibilityChecker:
    WITHIN = "Within Budget"
    EXACT = "Exactly Within Budget"
    OVER = "Over Budget"

    def check(self, breakdown, budget):
        if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
            raise ValidationError("Budget must be a positive whole number.")
        total = breakdown.total
        difference = budget - total
        if difference > 0:
            status = self.WITHIN
        elif difference == 0:
            status = self.EXACT
        else:
            status = self.OVER
        return FeasibilityResult(
            status, budget, total, difference,
            max(difference, 0), max(-difference, 0), difference >= 0,
            breakdown.subtotal <= budget < total,
        )

    def explain(self, result):
        if result.status == self.OVER:
            text = (f"Estimated cost {format_pkr(result.total)} exceeds the budget "
                    f"{format_pkr(result.budget)} by {format_pkr(result.shortage)}.")
            if result.emergency_is_deciding:
                text += " The emergency allowance is what pushes this trip over budget."
            return text
        if result.status == self.EXACT:
            return f"Estimated cost {format_pkr(result.total)} exactly matches your budget."
        return f"Within budget: {format_pkr(result.remaining)} remaining."
