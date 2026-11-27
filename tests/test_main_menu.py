import shutil

import pytest

from main import SmartLifePlanner
from utils.data_manager import PROJECT_ROOT


@pytest.fixture(autouse=True)
def seeded_dm(tmp_dm):
    """Give the temporary data folder the real destination data (never the real user data)."""
    (tmp_dm.data_dir).mkdir(parents=True, exist_ok=True)
    shutil.copy(PROJECT_ROOT / "data" / "destinations.json", tmp_dm.data_dir / "destinations.json")
    return tmp_dm


def run_app(tmp_dm, inputs):
    outputs, feed = [], iter(inputs)

    def fake_input(prompt=""):
        try:
            return next(feed)
        except StopIteration:
            raise EOFError from None

    app = SmartLifePlanner(tmp_dm, input_fn=fake_input, output_fn=outputs.append)
    app.run()
    return "\n".join(map(str, outputs)), app


def test_exit_immediately(tmp_dm):
    out, _ = run_app(tmp_dm, ["5"])
    assert "Goodbye" in out


@pytest.mark.parametrize("bad", ["abc", "", "0", "9", "-1"])
def test_invalid_menu_options_are_rejected_then_app_continues(tmp_dm, bad):
    out, _ = run_app(tmp_dm, [bad, "5"])
    assert "Invalid option" in out and "Goodbye" in out


def test_developer_info_menu(tmp_dm):
    out, _ = run_app(tmp_dm, ["4", "5"])
    assert "GitHub:" in out and "Email:" in out


def test_input_ending_unexpectedly_does_not_crash(tmp_dm):
    out, _ = run_app(tmp_dm, [])  # input closes immediately (EOF)
    assert "Input closed" in out


def test_budget_menu_requires_active_budget(tmp_dm):
    out, _ = run_app(tmp_dm, ["2", "7", "15", "5"])
    assert "Create or select a budget first" in out


def test_full_budget_flow_with_invalid_then_valid_input(tmp_dm):
    inputs = ["2", "1", "2026-11", "-5", "50000", "1",          # bad amount then valid
              "7", "Grocery", "1200", "milk", "2026-11-02", "",  # record expense
              "12", "15", "5"]
    out, app = run_app(tmp_dm, inputs)
    assert "Amount must be greater than zero" in out or "cannot be negative" in out
    assert "Recorded E001" in out and "Savings" in out
    assert app.budgets.get_budget("2026-11", "Home & Kitchen").total_actual == 1200


def test_trip_flow_cancel_keeps_nothing_saved(tmp_dm):
    inputs = ["1", "1", "400000", "2", "1", "4", "Hunza", "3", "2", "2", "", "", "8", "9", "5", "y"]
    out, app = run_app(tmp_dm, inputs)
    assert "PENDING" in out and "No saved trips yet" in out
    assert app.planner.confirmed is None and tmp_dm.load_trips() == []


def test_trip_pdf_without_confirmation_shows_error(tmp_dm):
    out, _ = run_app(tmp_dm, ["1", "7", "9", "5"])
    assert "Confirm the trip plan" in out


def test_app_starts_safely_without_destination_file(tmp_path):
    from utils.data_manager import DataManager
    out, _ = run_app(DataManager(tmp_path / "empty"), ["1", "1", "9", "5"])
    assert "No valid destinations" in out and "Goodbye" in out


# ---- extended end-to-end menu flows ----
NEW_TRIP = ["1", "1", "{budget}", "{pax}", "1", "4", "{dest}", "{days}", "{nights}", "2", "", ""]


def trip_inputs(budget=400000, pax=2, dest="Hunza", days=3, nights=2):
    return [x.format(budget=budget, pax=pax, dest=dest, days=days, nights=nights) for x in NEW_TRIP]


def test_confirm_trip_saves_view_itinerary_and_generate_pdf(tmp_dm):
    out, app = run_app(tmp_dm, trip_inputs() + ["2", "5", "7", "8", "9", "3", "5"])
    assert "Plan confirmed and saved" in out and "PDF created" in out and "Day 1" in out
    assert len(tmp_dm.load_trips()) == 1 and len(tmp_dm.load_reports()) == 1
    assert len(list(tmp_dm.reports_dir.glob("*.pdf"))) == 1
    assert "Generated reports" in out


def test_alternatives_shown_for_over_budget_trip(tmp_dm):
    out, _ = run_app(tmp_dm, trip_inputs(budget=60000, pax=4, days=5, nights=4) + ["3", "9", "5", "y"])
    assert "Shortage" in out and "Increase budget" in out and "ranked" in out


def test_alternatives_for_affordable_trip(tmp_dm):
    out, _ = run_app(tmp_dm, trip_inputs(budget=900000) + ["3", "9", "5", "y"])
    assert "no alternatives are needed" in out


def test_suggestions_when_destination_is_any(tmp_dm):
    inputs = ["1", "1", "150000", "4", "1", "4", "Any", "5", "4", "2", "", "", "1", "9", "5", "y"]
    out, app = run_app(tmp_dm, inputs)
    assert "[affordable]" in out and "[over budget]" in out
    assert app.planner.pending is not None


def test_modify_then_confirm_and_modify_then_cancel(tmp_dm):
    base = trip_inputs()
    confirm = base + ["5", "4", "travellers", "3", "", "y", "9", "5"]
    out, app = run_app(tmp_dm, confirm)
    assert "travellers: 2 -> 3" in out and "Changes confirmed" in out
    assert app.planner.confirmed.trip.travellers == 3

    cancel = base + ["5", "4", "travellers", "6", "budget", "1000", "", "n", "9", "5"]
    out, app = run_app(tmp_dm, cancel)
    assert "Changes cancelled" in out and app.planner.confirmed.trip.travellers == 2


def test_modify_with_invalid_value_reports_error(tmp_dm):
    out, app = run_app(tmp_dm, trip_inputs() + ["4", "travellers", "zero", "", "9", "5", "y"])
    assert "whole number" in out and app.planner.pending.trip.travellers == 2


def test_cancel_pending_and_view_without_plan(tmp_dm):
    out, _ = run_app(tmp_dm, ["1", "2", "6", "9", "5"])
    assert "No trip plan yet" in out and "Nothing to cancel" in out


def test_exit_with_pending_changes_can_be_declined(tmp_dm):
    out, app = run_app(tmp_dm, trip_inputs() + ["9", "5", "n", "5", "y"])
    assert app.planner.pending is not None and "Goodbye" in out


def test_invalid_trip_inputs_are_retried(tmp_dm):
    inputs = ["1", "1", "-5", "abc", "100000", "0", "2", "1", "4", "Alpha", "3", "2", "1", "x", "5", "y"]
    out, _ = run_app(tmp_dm, inputs[:-3] + ["9", "5"])
    assert "Budget must be at least 1" in out and "whole number" in out


def test_budget_full_lifecycle_and_pdf(tmp_dm):
    inputs = ["2", "1", "2026-11", "100000", "2",           # personal finance budget
              "3", "Pet Care", "2000",                       # custom category
              "6", "Shopping", "5000",                       # planned
              "7", "Shopping", "6000", "shoes", "2026-11-04", "S1",
              "10", "11", "12",
              "8", "S1", "", "5500", "", "",                 # update expense
              "9", "S1",                                     # delete
              "4", "Pet Care", "Pets", "2500",               # rename + planned
              "5", "Pets",                                   # remove
              "14",                                          # PDF before confirm -> error
              "13", "y", "14", "15", "3", "5"]
    out, app = run_app(tmp_dm, inputs)
    assert "Recorded S1" in out and "Warning: Shopping is over its planned amount" in out
    assert "Expense updated" in out and "Expense deleted" in out and "Category removed" in out
    assert "Confirm the monthly budget" in out and "Budget confirmed" in out and "PDF created" in out
    assert len(tmp_dm.load_budget_records()) == 1


def test_budget_select_existing_and_duplicate_creation(tmp_dm):
    inputs = ["2", "1", "2026-10", "5000", "1",
              "1", "2026-10", "6000", "1",                   # duplicate -> error
              "2", "1", "12", "15", "5"]
    out, _ = run_app(tmp_dm, inputs)
    assert "already exists" in out and "Home & Kitchen - 2026-10" in out


def test_budget_select_without_saved_budgets(tmp_dm):
    out, _ = run_app(tmp_dm, ["2", "2", "15", "5"])
    assert "No saved budgets" in out


def test_overall_overspending_warning_in_menu(tmp_dm):
    inputs = ["2", "1", "2026-11", "1000", "1", "7", "Rent", "1500", "r", "", "", "12", "15", "5"]
    out, _ = run_app(tmp_dm, inputs)
    assert "exceeds the monthly budget" in out


def test_previous_reports_when_none(tmp_dm):
    out, _ = run_app(tmp_dm, ["3", "5"])
    assert "No reports generated yet" in out
