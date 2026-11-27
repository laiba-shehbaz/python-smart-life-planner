"""MonthlyBudgetManager: owns all budgets, activity history and persistence."""
from collections import deque

from models.budget import BUDGET_CLASSES, create_budget, Budget
from utils.validators import ValidationError, validate_month


class MonthlyBudgetManager:
    def __init__(self, data_manager=None):
        self._budgets = {}
        self.data_manager = data_manager
        self.activity = deque(maxlen=15)  # recent activity history
        self.load_errors = []

    @staticmethod
    def key(month, budget_type):
        return f"{validate_month(month)}|{budget_type}"

    def create_budget(self, month, total_amount, budget_type):
        key = self.key(month, budget_type)
        if key in self._budgets:
            raise ValidationError(f"A {budget_type} budget for {month} already exists.")
        budget = create_budget(month, total_amount, budget_type)
        self._budgets[key] = budget
        self.activity.append(f"Created {budget_type} budget for {month}")
        self.save()
        return budget

    def get_budget(self, month, budget_type):
        budget = self._budgets.get(self.key(month, budget_type))
        if budget is None:
            raise ValidationError(f"No {budget_type} budget exists for {month}.")
        return budget

    def list_budgets(self):
        return sorted(self._budgets.values(), key=lambda b: (b.month, b.budget_type))

    def delete_budget(self, month, budget_type):
        self.get_budget(month, budget_type)
        del self._budgets[self.key(month, budget_type)]
        self.activity.append(f"Deleted {budget_type} budget for {month}")
        self.save()

    def confirm_budget(self, budget):
        budget.confirm()
        self.activity.append(f"Confirmed {budget.budget_type} budget for {budget.month}")
        self.save()

    def log(self, message):
        self.activity.append(message)

    def save(self):
        if self.data_manager is not None:
            self.data_manager.save_budget_records([b.to_dict() for b in self.list_budgets()])

    def load(self):
        """Load saved budgets; invalid or duplicate records are skipped and reported."""
        self._budgets, self.load_errors = {}, []
        if self.data_manager is None:
            return 0
        for record in self.data_manager.load_budget_records():
            try:
                budget = Budget.from_dict(record)
                key = self.key(budget.month, budget.budget_type)
                if key in self._budgets:
                    raise ValidationError(f"Duplicate budget {key} ignored.")
                self._budgets[key] = budget
            except ValidationError as exc:
                self.load_errors.append(str(exc))
        return len(self._budgets)

    @staticmethod
    def budget_types():
        return tuple(BUDGET_CLASSES)
