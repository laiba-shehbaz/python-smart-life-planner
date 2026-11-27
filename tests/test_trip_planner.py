import pytest
from dataclasses import replace

from models.trip import Trip
from services.trip_planner import build_itinerary
from utils.constants import MAX_DAYS, MAX_TRAVELLERS
from utils.validators import ValidationError


def make(**kw):
    data = dict(budget=100000, travellers=3, destination="Alpha", departure_city="Islamabad", days=3, nights=2)
    data.update(kw)
    return Trip(**data)


@pytest.mark.parametrize("kw", [
    {"budget": 0}, {"budget": -1}, {"budget": "abc"}, {"budget": ""},
    {"travellers": 0}, {"travellers": -2}, {"travellers": "two"}, {"travellers": MAX_TRAVELLERS + 1},
    {"days": 0}, {"days": "x"}, {"days": MAX_DAYS + 1},
    {"nights": -1}, {"days": 2, "nights": 3}, {"category": "Luxury"}, {"departure_city": "Atlantis"},
    {"transport": "Rocket"}, {"destination": "  "},
])
def test_invalid_trip_inputs_are_rejected(kw):
    with pytest.raises(ValidationError):
        make(**kw)


def test_trip_accepts_text_input_and_normalises():
    trip = make(budget="1,50,000", travellers="4", days="3", nights="0", category="premium", transport="auto")
    assert (trip.budget, trip.travellers, trip.nights, trip.category, trip.transport) == (150000, 4, 0, "Premium", None)


def test_maximum_traveller_limit_is_accepted(planner):
    plan = planner.evaluate(make(budget=10**9, travellers=MAX_TRAVELLERS))
    assert plan.breakdown.rooms == 25  # ceil(50 / 2)
    assert plan.feasibility.is_feasible


def test_evaluate_returns_costs_and_feasibility(planner):
    plan = planner.evaluate(make(budget=28820))
    assert plan.total == 28820
    assert plan.status == "Exactly Within Budget"


@pytest.mark.parametrize("budget,status", [(28819, "Over Budget"), (28820, "Exactly Within Budget"), (28821, "Within Budget")])
def test_budget_boundaries_through_planner(planner, budget, status):
    assert planner.evaluate(make(budget=budget)).status == status


def test_one_person_trip_is_affordable_with_small_budget(planner):
    plan = planner.evaluate(make(budget=6000, travellers=1, days=1, nights=0))
    assert plan.feasibility.is_feasible and plan.breakdown.rooms == 1


def test_unknown_destination_raises(planner):
    with pytest.raises(ValidationError, match="Unknown destination"):
        planner.evaluate(make(destination="Atlantis"))


def test_destination_lookup_is_case_insensitive(planner):
    assert planner.evaluate(make(destination="alpha")).trip.destination == "Alpha"


def test_unsupported_category_for_destination_raises(planner):
    with pytest.raises(ValidationError):
        planner.evaluate(make(destination="Gamma", category="Budget"))


# ---- dynamic modification ----
def test_modify_requires_existing_plan(planner):
    with pytest.raises(ValidationError):
        planner.modify(budget=5000)


def test_modify_travellers_recalculates_everything(planner):
    planner.propose(make())
    new = planner.modify(travellers=5)
    assert new.breakdown.transportation == 5000 and new.breakdown.rooms == 3
    assert new.breakdown.food == 500 * 5 * 3


def test_modify_nights_and_days_together(planner):
    planner.propose(make())
    new = planner.modify(days=5, nights=0)
    assert new.breakdown.accommodation == 0 and new.breakdown.food == 500 * 3 * 5


def test_modify_days_alone_below_nights_is_rejected_and_state_kept(planner):
    first = planner.propose(make(days=4, nights=3))
    with pytest.raises(ValidationError):
        planner.modify(days=2)
    assert planner.pending is first


def test_modify_destination_changes_costs(planner):
    planner.propose(make())
    assert planner.modify(destination="Beta").total != 28820


def test_modify_multiple_parameters_at_once(planner):
    planner.propose(make())
    new = planner.modify(budget=20000, travellers=2, destination="Beta", category="Budget")
    assert (new.trip.budget, new.trip.travellers, new.trip.destination, new.trip.category) == (20000, 2, "Beta", "Budget")
    assert new.status == planner.evaluate(new.trip).status


def test_repeated_budget_changes_flip_status(planner):
    planner.propose(make())
    assert planner.modify(budget=1000).status == "Over Budget"
    assert planner.modify(budget=28820).status == "Exactly Within Budget"
    assert planner.modify(budget=500000).status == "Within Budget"


@pytest.mark.parametrize("changes", [{"colour": "red"}, {}])
def test_modify_rejects_unknown_or_empty_changes(planner, changes):
    planner.propose(make())
    with pytest.raises(ValidationError):
        planner.modify(**changes)


def test_cancelled_changes_preserve_previous_confirmed_plan(planner):
    planner.propose(make())
    confirmed = planner.confirm()
    planner.modify(travellers=6, budget=10)
    assert planner.cancel() is True
    assert planner.pending is None and planner.confirmed is confirmed
    assert planner.confirmed.trip.travellers == 3


def test_unconfirmed_modification_does_not_overwrite_confirmed(planner):
    planner.propose(make())
    confirmed = planner.confirm()
    planner.modify(destination="Beta")
    assert planner.confirmed is confirmed  # e.g. user exits without confirming
    assert planner.current is planner.pending


def test_confirmed_changes_replace_plan_and_are_saved(planner, tmp_dm):
    planner.propose(make())
    planner.confirm()
    planner.modify(travellers=4)
    planner.confirm()
    assert planner.confirmed.trip.travellers == 4
    saved = tmp_dm.load_trips()
    assert len(saved) == 2 and saved[-1]["trip"]["travellers"] == 4
    assert saved[-1]["breakdown"]["total"] == planner.confirmed.total


def test_confirm_without_pending_raises(planner):
    with pytest.raises(ValidationError):
        planner.confirm()


def test_cancel_with_nothing_pending_returns_false(planner):
    assert planner.cancel() is False


def test_destination_change_after_recommendations(planner):
    planner.propose(make(budget=5000))
    report = planner.optimize()
    assert report.destination_options or report.notes
    alt = planner.modify(destination="Gamma", category="Premium")
    assert alt.trip.destination == "Gamma"


def test_diff_lists_only_changed_fields(planner):
    old = planner.propose(make())
    new = planner.modify(travellers=4)
    diff = planner.diff(old, new)
    assert diff["travellers"] == (3, 4) and "destination" not in diff and "total" in diff


def test_history_is_bounded(planner):
    planner.propose(make())
    for i in range(20):
        planner.modify(budget=1000 + i)
    assert len(planner.history) == 10


# ---- itinerary ----
@pytest.mark.parametrize("days,nights", [(1, 0), (2, 1), (3, 2), (5, 2), (4, 4)])
def test_itinerary_matches_days_and_nights(planner, days, nights):
    planner.propose(make(days=days, nights=nights))
    plan = planner.itinerary()
    assert len(plan) == days
    text = " ".join(" ".join(d.items) for d in plan)
    assert text.count("Overnight stay") == nights
    assert "Depart from Islamabad" in plan[0].items[0]
    assert "Return journey" in text or "return to Islamabad" in text


def test_zero_night_itinerary_has_no_check_in(planner):
    planner.propose(make(days=1, nights=0))
    day = planner.itinerary()[0]
    assert not any("Check in" in i or "Overnight" in i for i in day.items)
    assert day.title.startswith("Day trip")


def test_itinerary_without_plan_raises(planner):
    with pytest.raises(ValidationError):
        planner.itinerary()
