"""Monthly budget models. Budget is the base class; HomeKitchenBudget and
PersonalFinanceBudget inherit from it and only differ by default categories."""
from collections import Counter, defaultdict, namedtuple

from models.expense import Expense
from utils.calculations import money, percentage
from utils.constants import HOME_KITCHEN, PERSONAL_FINANCE
from utils.validators import (ValidationError, parse_amount, validate_category_name,
                              validate_date, validate_expense_id, validate_month)

CategoryRow = namedtuple("CategoryRow", "category planned actual difference")


class Budget:
    BUDGET_TYPE = "Custom"
    DEFAULT_CATEGORIES = ()

    def __init__(self, month, total_amount, budget_type=None):
        self._month = validate_month(month)
        self._total = parse_amount(total_amount, "Monthly budget")
        self._type = budget_type or self.BUDGET_TYPE
        self._planned = {name: 0.0 for name in self.DEFAULT_CATEGORIES}
        self._expenses = {}
        self._confirmed = False

    # ---- read-only properties (encapsulation) ----
    @property
    def month(self):
        return self._month

    @property
    def total_amount(self):
        return self._total

    @property
    def budget_type(self):
        return self._type

    @property
    def confirmed(self):
        return self._confirmed

    @property
    def categories(self):
        return dict(self._planned)

    @property
    def expenses(self):
        return sorted(self._expenses.values(), key=lambda e: (e.date, e.expense_id))

    def _touch(self):
        self._confirmed = False

    def confirm(self):
        self._confirmed = True

    # ---- categories ----
    def _resolve(self, name):
        wanted = validate_category_name(name).lower()
        for existing in self._planned:
            if existing.lower() == wanted:
                return existing
        raise ValidationError(f"Category '{name}' does not exist.")

    def has_category(self, name):
        try:
            self._resolve(name)
            return True
        except ValidationError:
            return False

    def add_category(self, name, planned=0):
        name = validate_category_name(name)
        if self.has_category(name):
            raise ValidationError(f"Category '{name}' already exists.")
        amount = parse_amount(planned, "Planned amount", allow_zero=True)
        self._planned[name] = amount
        self._touch()

    def set_planned(self, name, amount):
        name = self._resolve(name)
        self._planned[name] = parse_amount(amount, "Planned amount", allow_zero=True)
        self._touch()

    def rename_category(self, old, new):
        old = self._resolve(old)
        new = validate_category_name(new)
        if new.lower() != old.lower() and self.has_category(new):
            raise ValidationError(f"Category '{new}' already exists.")
        self._planned = {(new if k == old else k): v for k, v in self._planned.items()}
        for expense in self._expenses.values():
            if expense.category == old:
                expense.update(category=new)
        self._touch()

    def remove_category(self, name):
        name = self._resolve(name)
        if any(e.category == name for e in self._expenses.values()):
            raise ValidationError(f"Cannot remove '{name}': it has recorded expenses. Delete them first.")
        del self._planned[name]
        self._touch()

    def set_total(self, amount):
        self._total = parse_amount(amount, "Monthly budget")
        self._touch()

    # ---- expenses ----
    def _next_id(self):
        n = len(self._expenses) + 1
        while f"E{n:03d}" in self._expenses:
            n += 1
        return f"E{n:03d}"

    def add_expense(self, category, amount, description="", expense_date=None, expense_id=None):
        category = self._resolve(category)
        if expense_id is None or str(expense_id).strip() == "":
            expense_id = self._next_id()
        expense_id = validate_expense_id(expense_id)
        if expense_id in self._expenses:
            raise ValidationError(f"Expense ID '{expense_id}' already exists.")
        if expense_date:
            validate_date(expense_date, self._month)
        else:
            expense_date = f"{self._month}-01"
        expense = Expense(expense_id, category, amount, description, expense_date)
        self._expenses[expense_id] = expense
        self._touch()
        return expense

    def get_expense(self, expense_id):
        expense = self._expenses.get(str(expense_id).strip())
        if expense is None:
            raise ValidationError(f"Expense '{expense_id}' does not exist.")
        return expense

    def update_expense(self, expense_id, category=None, amount=None, description=None, expense_date=None):
        expense = self.get_expense(expense_id)
        if category is not None:
            category = self._resolve(category)
        if expense_date is not None:
            validate_date(expense_date, self._month)
        expense.update(category, amount, description, expense_date)
        self._touch()
        return expense

    def delete_expense(self, expense_id):
        expense = self.get_expense(expense_id)
        del self._expenses[expense.expense_id]
        self._touch()
        return expense

    # ---- calculations ----
    def expenses_by_category(self):
        grouped = defaultdict(list)
        for expense in self.expenses:
            grouped[expense.category].append(expense)
        return grouped

    def actual_by_category(self):
        totals = Counter()
        for expense in self._expenses.values():
            totals[expense.category] += expense.amount
        return totals

    @property
    def total_planned(self):
        return money(sum(self._planned.values()))

    @property
    def total_actual(self):
        return money(sum(e.amount for e in self._expenses.values()))

    @property
    def unallocated(self):
        return money(self._total - self.total_planned)

    @property
    def is_over_allocated(self):
        return self.total_planned > self._total

    @property
    def remaining_balance(self):
        return money(self._total - self.total_actual)

    @property
    def savings(self):
        return max(0.0, self.remaining_balance)

    @property
    def savings_percentage(self):
        return percentage(self.savings, self._total)

    @property
    def is_overspent(self):
        return self.total_actual > self._total

    def category_rows(self):
        actual = self.actual_by_category()
        return [CategoryRow(name, planned, money(actual[name]), money(planned - actual[name]))
                for name, planned in self._planned.items()]

    def overspent_categories(self):
        return [row for row in self.category_rows() if row.actual > row.planned]

    def summary(self):
        return {
            "month": self._month, "budget_type": self._type, "total_amount": self._total,
            "rows": [tuple(r) for r in self.category_rows()],
            "total_planned": self.total_planned, "total_actual": self.total_actual,
            "remaining_balance": self.remaining_balance, "savings": self.savings,
            "savings_percentage": self.savings_percentage,
            "overspent": [tuple(r) for r in self.overspent_categories()],
            "unallocated": self.unallocated, "overall_overspent": self.is_overspent,
            "over_allocated": self.is_over_allocated, "expense_count": len(self._expenses),
            "confirmed": self._confirmed,
        }

    # ---- persistence ----
    def to_dict(self):
        return {"month": self._month, "total_amount": self._total, "budget_type": self._type,
                "categories": self._planned, "expenses": [e.to_dict() for e in self.expenses],
                "confirmed": self._confirmed}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValidationError("Budget record must be an object.")
        for key in ("month", "total_amount", "budget_type", "categories"):
            if key not in data:
                raise ValidationError(f"Budget record is missing '{key}'.")
        budget = create_budget(data["month"], data["total_amount"], data["budget_type"])
        budget._planned = {}
        if not isinstance(data["categories"], dict):
            raise ValidationError("Budget categories must be an object.")
        for name, planned in data["categories"].items():
            budget.add_category(name, planned)
        for item in data.get("expenses", []):
            expense = Expense.from_dict(item)
            budget.add_expense(expense.category, expense.amount, expense.description,
                               expense.date, expense.expense_id)
        budget._confirmed = bool(data.get("confirmed", False))
        return budget


class HomeKitchenBudget(Budget):
    BUDGET_TYPE = HOME_KITCHEN
    DEFAULT_CATEGORIES = ("Grocery", "Electricity", "Gas", "Water", "Internet", "Rent",
                          "Kitchen Supplies", "Medical Expenses", "Transportation",
                          "Emergency Savings", "Other Expenses")


class PersonalFinanceBudget(Budget):
    BUDGET_TYPE = PERSONAL_FINANCE
    DEFAULT_CATEGORIES = ("Cosmetics and Personal Care", "Fitness and Gym", "Health and Medical",
                          "Shopping", "Clothing", "Food and Restaurants", "Transportation",
                          "Education", "Entertainment", "Investments and Savings",
                          "Other Expenses")


BUDGET_CLASSES = {HOME_KITCHEN: HomeKitchenBudget, PERSONAL_FINANCE: PersonalFinanceBudget}


def create_budget(month, total_amount, budget_type):
    """Factory: pick the right Budget subclass from the budget type name."""
    cls = BUDGET_CLASSES.get(budget_type)
    if cls is None:
        raise ValidationError(f"Unknown budget type '{budget_type}'. Choose: {', '.join(BUDGET_CLASSES)}.")
    return cls(month, total_amount)
