import pytest

from models.budget import Budget, create_budget
from utils.validators import ValidationError


@pytest.fixture
def home():
    b = create_budget("2026-11", 100000, "Home & Kitchen")
    b.set_planned("Grocery", 30000)
    b.set_planned("Rent", 40000)
    return b


@pytest.mark.parametrize("amount", [0, -1, "abc", "", None])
def test_invalid_monthly_amounts_rejected(amount):
    with pytest.raises(ValidationError):
        create_budget("2026-11", amount, "Home & Kitchen")


def test_invalid_month_and_type_rejected():
    with pytest.raises(ValidationError):
        create_budget("November", 1000, "Home & Kitchen")
    with pytest.raises(ValidationError):
        create_budget("2026-11", 1000, "Business")


def test_budget_types_have_expected_default_categories():
    home = create_budget("2026-11", 1000, "Home & Kitchen")
    personal = create_budget("2026-11", 1000, "Personal Finance")
    assert "Grocery" in home.categories and "Fitness and Gym" in personal.categories
    assert isinstance(home, Budget) and home.budget_type == "Home & Kitchen"


def test_add_custom_category_and_reject_duplicates(home):
    home.add_category("Pet Care", 2000)
    assert home.categories["Pet Care"] == 2000
    for dup in ("Pet Care", "pet care", "GROCERY"):
        with pytest.raises(ValidationError):
            home.add_category(dup)


@pytest.mark.parametrize("name", ["", "  ", "9lives", "bad$name"])
def test_invalid_custom_categories_rejected(home, name):
    with pytest.raises(ValidationError):
        home.add_category(name)


def test_negative_planned_amount_rejected(home):
    with pytest.raises(ValidationError):
        home.set_planned("Grocery", -5)
    with pytest.raises(ValidationError):
        home.add_category("Extra", -1)


def test_rename_and_remove_category(home):
    home.add_expense("Grocery", 500, "milk", "2026-11-02")
    home.rename_category("Grocery", "Food Shopping")
    assert home.expenses[0].category == "Food Shopping"
    with pytest.raises(ValidationError):
        home.remove_category("Food Shopping")  # has expenses
    home.remove_category("Gas")
    assert "Gas" not in home.categories


def test_record_update_and_delete_expense(home):
    e = home.add_expense("Grocery", 1000, "rice", "2026-11-03")
    assert e.expense_id == "E001"
    home.update_expense("E001", amount=1500, description="rice and oil")
    assert home.expenses[0].amount == 1500 and home.expenses[0].description == "rice and oil"
    home.delete_expense("E001")
    assert home.expenses == []


def test_auto_ids_are_unique_after_deletion(home):
    home.add_expense("Grocery", 1, "a")
    home.add_expense("Grocery", 1, "b")
    home.delete_expense("E001")
    home.add_expense("Grocery", 1, "c")
    ids = [e.expense_id for e in home.expenses]
    assert len(ids) == len(set(ids))


def test_duplicate_and_invalid_expense_ids(home):
    home.add_expense("Grocery", 100, "x", "2026-11-01", expense_id="X1")
    with pytest.raises(ValidationError):
        home.add_expense("Grocery", 100, "y", "2026-11-01", expense_id="X1")
    with pytest.raises(ValidationError):
        home.add_expense("Grocery", 100, "y", "2026-11-01", expense_id="bad id!")


@pytest.mark.parametrize("amount", [0, -10, "abc", "", None])
def test_invalid_expense_amounts_rejected(home, amount):
    with pytest.raises(ValidationError):
        home.add_expense("Grocery", amount, "x")


def test_expense_for_unknown_category_or_wrong_month(home):
    with pytest.raises(ValidationError):
        home.add_expense("Spaceships", 10, "x")
    with pytest.raises(ValidationError):
        home.add_expense("Grocery", 10, "x", "2026-12-01")


@pytest.mark.parametrize("op", ["update", "delete"])
def test_nonexistent_expense_update_and_delete(home, op):
    with pytest.raises(ValidationError, match="does not exist"):
        if op == "update":
            home.update_expense("NOPE", amount=5)
        else:
            home.delete_expense("NOPE")


def test_failed_update_changes_nothing(home):
    home.add_expense("Grocery", 100, "x", "2026-11-01")
    with pytest.raises(ValidationError):
        home.update_expense("E001", amount=-5)
    assert home.expenses[0].amount == 100


def test_totals_remaining_savings_and_percentage(home):
    home.add_expense("Grocery", 25000, "g", "2026-11-02")
    home.add_expense("Rent", 40000, "r", "2026-11-01")
    assert home.total_planned == 70000
    assert home.total_actual == 65000
    assert home.remaining_balance == 35000
    assert home.savings == 35000 and home.savings_percentage == 35.0
    assert home.unallocated == 30000


def test_category_overspending_detected(home):
    home.add_expense("Grocery", 32000, "big shop", "2026-11-02")
    over = home.overspent_categories()
    assert [(r.category, r.actual - r.planned) for r in over] == [("Grocery", 2000)]
    assert not home.is_overspent


def test_spending_in_unplanned_category_counts_as_overspending(home):
    home.add_expense("Gas", 10, "cylinder", "2026-11-02")
    assert [r.category for r in home.overspent_categories()] == ["Gas"]


def test_overall_overspending_and_zero_savings(home):
    home.add_expense("Rent", 105000, "everything", "2026-11-01")
    assert home.is_overspent and home.savings == 0 and home.savings_percentage == 0
    assert home.remaining_balance == -5000


def test_exactly_all_money_spent_gives_zero_savings(home):
    home.add_expense("Rent", 100000, "all", "2026-11-01")
    assert home.remaining_balance == 0 and home.savings == 0 and not home.is_overspent


def test_empty_expenses(home):
    assert home.expenses == [] and home.total_actual == 0 and home.savings == 100000
    assert home.savings_percentage == 100.0 and home.overspent_categories() == []


def test_planned_exceeds_budget_is_flagged(home):
    home.set_planned("Electricity", 50000)
    assert home.is_over_allocated and home.unallocated == -20000


def test_all_money_allocated_has_zero_unallocated(home):
    home.set_planned("Electricity", 30000)
    assert home.unallocated == 0 and not home.is_over_allocated


def test_collections_group_and_count(home):
    home.add_expense("Grocery", 100, "a", "2026-11-01")
    home.add_expense("Grocery", 50, "b", "2026-11-02")
    home.add_expense("Rent", 10, "c", "2026-11-03")
    grouped = home.expenses_by_category()
    assert len(grouped["Grocery"]) == 2 and len(grouped["Rent"]) == 1
    totals = home.actual_by_category()
    assert totals["Grocery"] == 150 and totals["Missing"] == 0


def test_editing_confirmed_budget_resets_confirmation(home):
    home.confirm()
    assert home.confirmed
    home.add_expense("Grocery", 1, "x", "2026-11-01")
    assert not home.confirmed


def test_round_trip_serialisation(home):
    home.add_category("Pets", 100)
    home.add_expense("Pets", 40.5, "food", "2026-11-04", "P1")
    clone = Budget.from_dict(home.to_dict())
    assert clone.summary() == home.summary()


@pytest.mark.parametrize("record", [None, {}, {"month": "2026-11"}, {"month": "bad", "total_amount": 1, "budget_type": "Home & Kitchen", "categories": {}}])
def test_from_dict_rejects_bad_records(record):
    with pytest.raises(ValidationError):
        Budget.from_dict(record)


def test_manager_create_duplicate_and_lookup(budget_manager):
    budget_manager.create_budget("2026-11", 5000, "Home & Kitchen")
    with pytest.raises(ValidationError):
        budget_manager.create_budget("2026-11", 6000, "Home & Kitchen")
    budget_manager.create_budget("2026-11", 6000, "Personal Finance")
    assert len(budget_manager.list_budgets()) == 2
    with pytest.raises(ValidationError):
        budget_manager.get_budget("2027-01", "Home & Kitchen")


def test_manager_saves_and_loads(budget_manager, tmp_dm):
    b = budget_manager.create_budget("2026-11", 5000, "Home & Kitchen")
    b.add_expense("Grocery", 100, "x", "2026-11-02")
    budget_manager.save()
    from services.budget_manager import MonthlyBudgetManager
    fresh = MonthlyBudgetManager(tmp_dm)
    assert fresh.load() == 1
    assert fresh.get_budget("2026-11", "Home & Kitchen").total_actual == 100


def test_manager_activity_history_is_a_bounded_deque(budget_manager):
    for m in range(1, 13):
        budget_manager.create_budget(f"2026-{m:02d}", 1000, "Home & Kitchen")
        budget_manager.create_budget(f"2026-{m:02d}", 1000, "Personal Finance")
    assert len(budget_manager.activity) == 15
    assert "2026-12" in budget_manager.activity[-1]
