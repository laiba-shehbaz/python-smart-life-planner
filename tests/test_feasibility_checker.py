import pytest
from dataclasses import replace

from services.feasibility_checker import TripFeasibilityChecker
from services.trip_calculator import TripCostCalculator
from utils.validators import ValidationError

TOTAL = 28820


@pytest.fixture
def checker():
    return TripFeasibilityChecker()


@pytest.fixture
def breakdown(destinations, settings, base_trip):
    return TripCostCalculator(settings).calculate(destinations[0], base_trip)


def test_exact_budget_boundary(checker, breakdown):
    result = checker.check(breakdown, TOTAL)
    assert result.status == "Exactly Within Budget"
    assert result.is_feasible and result.remaining == 0 and result.shortage == 0


def test_one_rupee_below_is_over_budget(checker, breakdown):
    result = checker.check(breakdown, TOTAL - 1)
    assert result.status == "Over Budget"
    assert not result.is_feasible and result.shortage == 1


def test_one_rupee_above_is_within_budget(checker, breakdown):
    result = checker.check(breakdown, TOTAL + 1)
    assert result.status == "Within Budget"
    assert result.remaining == 1 and result.shortage == 0


@pytest.mark.parametrize("budget,status", [(1, "Over Budget"), (28819, "Over Budget"), (28820, "Exactly Within Budget"), (28821, "Within Budget"), (10**8, "Within Budget")])
def test_status_classification(checker, breakdown, budget, status):
    assert checker.check(breakdown, budget).status == status


def test_emergency_allowance_can_make_trip_unaffordable(checker, breakdown):
    result = checker.check(breakdown, breakdown.subtotal)  # covers costs but not the emergency fund
    assert result.status == "Over Budget" and result.emergency_is_deciding
    assert result.shortage == breakdown.emergency


def test_emergency_not_deciding_when_far_over(checker, breakdown):
    assert not checker.check(breakdown, 1000).emergency_is_deciding


@pytest.mark.parametrize("budget", [0, -5, "1000", None, 12.5])
def test_invalid_budget_rejected(checker, breakdown, budget):
    with pytest.raises(ValidationError):
        checker.check(breakdown, budget)


def test_explanations_mention_shortage(checker, breakdown):
    assert "PKR 1" in checker.explain(checker.check(breakdown, TOTAL - 1))
    assert "exactly" in checker.explain(checker.check(breakdown, TOTAL))
    assert "remaining" in checker.explain(checker.check(breakdown, TOTAL + 500))
