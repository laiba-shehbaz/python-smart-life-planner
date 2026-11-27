import pytest
from dataclasses import replace

from models.trip import Trip
from services.trip_calculator import TripCostCalculator
from utils.validators import ValidationError


def make(**kw):
    data = dict(budget=20000, travellers=3, destination="Alpha", departure_city="Islamabad", days=3, nights=2)
    data.update(kw)
    return Trip(**data)


@pytest.fixture
def optimizer(planner):
    return planner.optimizer


def test_minimum_budget_and_additional_amount(optimizer):
    required, additional = optimizer.minimum_budget(make())
    assert required == 28820 and additional == 8820


def test_additional_budget_is_zero_when_affordable(optimizer):
    assert optimizer.minimum_budget(make(budget=50000))[1] == 0


def test_max_travellers_is_largest_affordable_count(optimizer):
    trip = make()
    n = optimizer.max_affordable_travellers(trip)
    assert 1 <= n < 3
    assert optimizer._cost(replace(trip, travellers=n)).total <= trip.budget
    assert optimizer._cost(replace(trip, travellers=n + 1)).total > trip.budget


def test_budget_insufficient_for_one_traveller(optimizer):
    trip = make(budget=100)
    assert optimizer.max_affordable_travellers(trip) == 0
    report = optimizer.analyse(trip)
    assert report.traveller_option is None
    assert any("even one traveller" in n for n in report.notes)


def test_feasible_durations_fit_budget(optimizer):
    trip = make(days=6, nights=5)
    options = optimizer.feasible_durations(trip)
    assert options
    for days, nights, total in options:
        assert total <= trip.budget and nights <= days
        assert optimizer._cost(replace(trip, days=days, nights=nights)).total == total


def test_minimum_duration_still_unaffordable(optimizer):
    report = optimizer.analyse(make(budget=500))
    assert report.duration_options == []
    assert any("shortest practical trip" in n for n in report.notes)


def test_no_destination_affordable(optimizer):
    report = optimizer.analyse(make(budget=500))
    assert report.destination_options == [] and report.ranked == []
    assert any("No other destination" in n for n in report.notes)
    assert any("minimum required budget" in n for n in report.notes)


def test_every_recommended_alternative_fits_budget(optimizer):
    trip = make(budget=15000)
    report = optimizer.analyse(trip)
    assert report.ranked
    calc = optimizer.calculator
    for alt in report.ranked:
        recomputed = calc.calculate(optimizer.destinations[alt.trip.destination], alt.trip)
        assert recomputed.total == alt.breakdown.total <= trip.budget


def test_alternatives_are_calculated_not_hardcoded(optimizer):
    small = optimizer.analyse(make(budget=9000))
    big = optimizer.analyse(make(budget=25000))
    assert {a.label for a in small.ranked} != {a.label for a in big.ranked}
    assert small.minimum_budget == big.minimum_budget == 28820


def test_ranking_is_sorted_by_score(optimizer):
    scores = [a.score for a in optimizer.analyse(make(budget=15000)).ranked]
    assert scores == sorted(scores, reverse=True)


def test_destination_options_exclude_current_and_unaffordable(optimizer):
    report = optimizer.analyse(make(budget=10000))
    names = {a.trip.destination for a in report.destination_options}
    assert "Alpha" not in names
    assert all(a.breakdown.total <= 10000 for a in report.destination_options)


def test_destination_comparison_respects_category_support(optimizer):
    names = [r.name for r in optimizer.compare_destinations(make(category="Budget"))]
    assert "Gamma" not in names and {"Alpha", "Beta"} <= set(names)


def test_destination_type_filter(optimizer):
    rows = optimizer.compare_destinations(make(destination_type="Historical Places", category="Premium"))
    assert [r.name for r in rows] == ["Gamma"]


def test_preference_alternatives_are_cheaper_combos(optimizer):
    report = optimizer.analyse(make(budget=26000))
    assert report.preference_options
    assert all(p.breakdown.total <= 26000 for p in report.preference_options)
    assert all((p.breakdown.transport_mode, p.breakdown.accommodation_type) != ("Car", "Hotel") for p in report.preference_options)


def test_within_budget_trip_has_no_alternatives(optimizer):
    report = optimizer.analyse(make(budget=50000))
    assert report.shortage == 0 and report.ranked == []


def test_unknown_destination_in_analysis(optimizer):
    with pytest.raises(ValidationError):
        optimizer.analyse(make(destination="Nowhere"))


def test_rank_prefers_same_destination_and_more_travellers(optimizer):
    report = optimizer.analyse(make(budget=15000))
    best = report.ranked[0]
    assert best.score >= report.ranked[-1].score
