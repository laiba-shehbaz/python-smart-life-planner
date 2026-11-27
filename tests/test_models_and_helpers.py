"""Extra tests: models, helpers, itinerary edge cases, persistence and report text."""
import dataclasses
import json
from datetime import date

import pytest

from models.destination import Destination
from models.expense import Expense
from models.trip import Trip, TripPlan
from services.budget_manager import MonthlyBudgetManager
from services.trip_calculator import TripCostCalculator
from services.trip_optimizer import WEIGHTS
from services.trip_planner import build_itinerary
from utils import calculations as calc
from utils.constants import DEFAULT_SETTINGS, TRAVEL_CATEGORIES
from utils.data_manager import build_settings
from utils.validators import ValidationError


def dest_dict(**over):
    data = {"name": "Alpha", "region": "R", "category": "Mountains", "transport_cost_pp": 1000,
            "accommodation_per_room_night": 4000, "food_pp_day": 500, "activities_pp_day": 200,
            "misc_pp_day": 100, "room_capacity": 2, "travel_categories": ["Standard"],
            "transport_modes": ["Car"], "accommodation_types": ["Hotel"],
            "highlights": ["Sight"], "activities": ["Act"]}
    data.update(over)
    return data


def trip(**kw):
    d = dict(budget=100000, travellers=3, destination="Alpha", departure_city="Islamabad", days=3, nights=2)
    d.update(kw)
    return Trip(**d)


# ---------------- Destination ----------------
def test_destination_round_trip():
    d = Destination.from_dict(dest_dict())
    assert Destination.from_dict(d.to_dict()) == d


def test_destination_is_immutable():
    d = Destination.from_dict(dest_dict())
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.name = "Other"


@pytest.mark.parametrize("over", [
    {"region": ""}, {"category": "Deserts"}, {"room_capacity": 0}, {"room_capacity": 21},
    {"transport_cost_pp": -1}, {"food_pp_day": "free"}, {"travel_categories": []},
    {"transport_modes": ["Rocket"]}, {"accommodation_types": "Hotel"}, {"name": ""},
])
def test_destination_rejects_invalid_fields(over):
    with pytest.raises(ValidationError):
        Destination.from_dict(dest_dict(**over))


@pytest.mark.parametrize("missing", ["region", "transport_cost_pp", "room_capacity", "travel_categories"])
def test_destination_rejects_missing_fields(missing):
    data = dest_dict()
    del data[missing]
    with pytest.raises(ValidationError):
        Destination.from_dict(data)


def test_destination_defaults_for_missing_highlights():
    data = dest_dict()
    del data["highlights"], data["activities"]
    assert Destination.from_dict(data).highlights == ("Local sightseeing",)


# ---------------- Trip / TripPlan ----------------
def test_trip_is_immutable_and_round_trips():
    t = trip(category="premium", transport="Car")
    assert Trip.from_dict(t.to_dict()) == t
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.budget = 5


@pytest.mark.parametrize("record", [None, "x", {}, {"budget": 5}])
def test_trip_from_dict_rejects_bad_records(record):
    with pytest.raises(ValidationError):
        Trip.from_dict(record)


@pytest.mark.parametrize("value", ["Auto", "AUTO", "none", "", None])
def test_trip_auto_preferences_become_none(value):
    assert trip(transport=value, accommodation=value).transport is None


def test_trip_plan_to_dict_has_all_sections(planner):
    plan = planner.evaluate(trip())
    assert isinstance(plan, TripPlan)
    d = plan.to_dict()
    assert set(d) == {"trip", "breakdown", "feasibility"}
    assert d["breakdown"]["total"] == plan.total == 28820
    json.dumps(d)  # must be JSON serialisable


# ---------------- Expense ----------------
def test_expense_defaults_and_round_trip():
    e = Expense("E1", "Grocery", 250.5, "", None)
    assert e.date == date.today().isoformat() and e.description == "No description"
    assert Expense.from_dict(e.to_dict()).to_dict() == e.to_dict()


def test_expense_update_is_all_or_nothing():
    e = Expense("E1", "Grocery", 100, "milk", "2026-11-01")
    with pytest.raises(ValidationError):
        e.update(category="Rent", amount="bad")
    assert (e.category, e.amount) == ("Grocery", 100)
    e.update(amount=150, description="rice")
    assert (e.amount, e.description) == (150, "rice")


@pytest.mark.parametrize("record", [None, {}, {"expense_id": "E1"}, {"expense_id": "E1", "category": "Rent"}])
def test_expense_from_dict_rejects_incomplete(record):
    with pytest.raises(ValidationError):
        Expense.from_dict(record)


@pytest.mark.parametrize("kw", [{"expense_id": "bad id"}, {"category": ""}, {"amount": 0}, {"description": "x" * 101}, {"expense_date": "2026-13-01"}])
def test_expense_rejects_invalid_values(kw):
    args = dict(expense_id="E1", category="Rent", amount=10, description="d", expense_date="2026-11-01")
    args.update(kw)
    with pytest.raises(ValidationError):
        Expense(**args)


# ---------------- calculation helpers ----------------
@pytest.mark.parametrize("value,expected", [(0.4, 0), (0.5, 1), (2.5, 3), (999.49, 999), (1000.5, 1001)])
def test_round_pkr_rounds_half_up(value, expected):
    assert calc.round_pkr(value) == expected


@pytest.mark.parametrize("part,whole,expected", [(0, 100, 0.0), (50, 100, 50.0), (1, 3, 33.33), (10, 0, 0.0)])
def test_percentage(part, whole, expected):
    assert calc.percentage(part, whole) == expected


@pytest.mark.parametrize("travellers,capacity", [(0, 2), (-1, 2), (2, 0)])
def test_rooms_required_rejects_invalid(travellers, capacity):
    with pytest.raises(ValueError):
        calc.rooms_required(travellers, capacity)


@pytest.mark.parametrize("amount,text", [(0, "PKR 0"), (999, "PKR 999"), (1000, "PKR 1,000"), (1234.5, "PKR 1,234.50"), (-2500, "-PKR 2,500")])
def test_format_pkr(amount, text):
    assert calc.format_pkr(amount) == text


def test_default_settings_are_complete_and_consistent():
    assert set(DEFAULT_SETTINGS["category_defaults"]) == set(TRAVEL_CATEGORIES)
    assert set(DEFAULT_SETTINGS["category_multipliers"]) == set(TRAVEL_CATEGORIES)
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_build_settings_category_defaults_override():
    s, errors = build_settings({"category_defaults": {"Budget": {"transport": "Car", "accommodation": "Hotel"}}})
    assert s["category_defaults"]["Budget"]["transport"] == "Car" and errors == []


# ---------------- calculator edge cases ----------------
def test_local_travel_between_twin_cities_is_cheap(settings):
    islamabad = Destination.from_dict(dest_dict(name="Islamabad", transport_cost_pp=2000))
    calc_ = TripCostCalculator(settings)
    local = calc_.calculate(islamabad, trip(destination="Islamabad", departure_city="Rawalpindi"))
    far = calc_.calculate(islamabad, trip(destination="Islamabad", departure_city="Karachi"))
    assert local.transportation == round(2000 * 0.15) * 3
    assert far.transportation > local.transportation


def test_unoffered_transport_or_accommodation_raises(settings):
    d = Destination.from_dict(dest_dict())
    with pytest.raises(ValidationError):
        TripCostCalculator(settings).calculate(d, trip(transport="Flight"))
    with pytest.raises(ValidationError):
        TripCostCalculator(settings).calculate(d, trip(accommodation="Resort"))


def test_default_preference_falls_back_to_first_offered(settings):
    d = Destination.from_dict(dest_dict(accommodation_types=["Guest House"], transport_modes=["Bus"]))
    b = TripCostCalculator(settings).calculate(d, trip())
    assert (b.transport_mode, b.accommodation_type) == ("Bus", "Guest House")


# ---------------- itinerary ----------------
def itin(days, nights):
    d = Destination.from_dict(dest_dict())
    return build_itinerary(d, trip(days=days, nights=nights), "Car", "Hotel", 2)


def test_itinerary_titles():
    days = itin(4, 3)
    assert [d.title for d in days] == ["Departure and arrival", "Sightseeing and activities",
                                       "Sightseeing and activities", "Final sightseeing and return"]


def test_itinerary_day_use_days_are_marked():
    text = " ".join(" ".join(d.items) for d in itin(5, 1))
    assert text.count("Day-use only") == 3 and text.count("Overnight stay") == 1


def test_itinerary_last_night_returns_next_morning():
    last = itin(3, 3)[-1].items[-1]
    assert "next morning" in last


def test_itinerary_mentions_rooms_and_cycles_highlights():
    days = itin(3, 2)
    assert "2 rooms" in days[0].items[2]
    assert all("Sightseeing: Sight." in " ".join(d.items) for d in days)  # single highlight cycles


# ---------------- planner extras ----------------
def test_evaluate_does_not_change_planner_state(planner):
    planner.evaluate(trip())
    assert planner.pending is None and planner.confirmed is None and len(planner.history) == 0


def test_second_proposal_replaces_pending(planner):
    planner.propose(trip(travellers=2))
    second = planner.propose(trip(travellers=4))
    assert planner.pending is second


def test_unknown_destination_message_lists_available(planner):
    with pytest.raises(ValidationError, match="Alpha"):
        planner.find_destination("Nowhere")


def test_save_failure_keeps_pending_plan(planner, tmp_dm, monkeypatch):
    planner.propose(trip())
    def boom(_):
        raise OSError("disk full")
    monkeypatch.setattr(tmp_dm, "save_trip", boom)
    with pytest.raises(OSError):
        planner.confirm()
    assert planner.confirmed is None and planner.pending is not None


# ---------------- optimizer extras ----------------
def test_compare_destinations_sorted_by_total(planner):
    rows = planner.optimizer.compare_destinations(trip())
    totals = [r.total for r in rows]
    assert totals == sorted(totals) and all(r.affordable == (r.total <= 100000) for r in rows)


def test_scores_are_between_zero_and_one(planner):
    report = planner.optimizer.analyse(trip(budget=15000))
    assert report.ranked and all(0 < a.score <= 1 for a in report.ranked)


def test_unchanged_trip_scores_highest_possible(planner):
    opt = planner.optimizer
    t = trip(budget=100000)
    cost = opt._cost(t)
    assert opt.score(t, cost, t, cost) == pytest.approx(0.25 + 0.25 + 0.20 + 0.15 * (1 - cost.total / 100000) + 0.15, abs=1e-4)


# ---------------- budget manager persistence ----------------
def test_manager_load_skips_corrupt_and_duplicate_records(tmp_dm):
    good = MonthlyBudgetManager(tmp_dm)
    good.create_budget("2026-11", 5000, "Home & Kitchen")
    records = tmp_dm.load_budget_records()
    tmp_dm.save_budget_records(records + records + [{"month": "bad"}])
    fresh = MonthlyBudgetManager(tmp_dm)
    assert fresh.load() == 1 and len(fresh.load_errors) == 2


def test_manager_delete_budget(budget_manager):
    budget_manager.create_budget("2026-11", 5000, "Home & Kitchen")
    budget_manager.delete_budget("2026-11", "Home & Kitchen")
    assert budget_manager.list_budgets() == []
    with pytest.raises(ValidationError):
        budget_manager.delete_budget("2026-11", "Home & Kitchen")


def test_manager_rejects_bad_month_and_unknown_type(budget_manager):
    with pytest.raises(ValidationError):
        budget_manager.create_budget("Nov", 5000, "Home & Kitchen")
    with pytest.raises(ValidationError):
        budget_manager.create_budget("2026-11", 5000, "Gaming")


def test_manager_without_data_manager_works_in_memory():
    m = MonthlyBudgetManager()
    m.create_budget("2026-11", 100, "Personal Finance")
    m.save()
    assert m.load() == 0


# ---------------- report text ----------------
def test_trip_text_uses_shortage_or_remaining_label(planner, reports):
    over = reports.trip_text(reports.trip_summary(planner.evaluate(trip(budget=1000)), planner.find_destination("Alpha")))
    ok = reports.trip_text(reports.trip_summary(planner.evaluate(trip()), planner.find_destination("Alpha")))
    assert "Shortage: PKR 27,820" in over and "Remaining: PKR 71,180" in ok
