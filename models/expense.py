"""Expense model."""
from datetime import date

from utils.validators import (ValidationError, parse_amount, validate_category_name,
                              validate_date, validate_description, validate_expense_id)


class Expense:
    """A single recorded (actual) expense."""

    def __init__(self, expense_id, category, amount, description="", expense_date=None):
        self._id = validate_expense_id(expense_id)
        self._category = validate_category_name(category)
        self._amount = parse_amount(amount, "Expense amount")
        self._description = validate_description(description)
        self._date = validate_date(expense_date or date.today().isoformat())

    @property
    def expense_id(self):
        return self._id

    @property
    def category(self):
        return self._category

    @property
    def amount(self):
        return self._amount

    @property
    def description(self):
        return self._description

    @property
    def date(self):
        return self._date

    def update(self, category=None, amount=None, description=None, expense_date=None):
        """Validate every changed field first, then apply (all-or-nothing)."""
        new = (
            validate_category_name(category) if category is not None else self._category,
            parse_amount(amount, "Expense amount") if amount is not None else self._amount,
            validate_description(description) if description is not None else self._description,
            validate_date(expense_date) if expense_date is not None else self._date,
        )
        self._category, self._amount, self._description, self._date = new

    def to_dict(self):
        return {"expense_id": self._id, "category": self._category, "amount": self._amount,
                "description": self._description, "date": self._date}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValidationError("Expense record must be an object.")
        for key in ("expense_id", "category", "amount"):
            if key not in data:
                raise ValidationError(f"Expense record is missing '{key}'.")
        return cls(data["expense_id"], data["category"], data["amount"],
                   data.get("description", ""), data.get("date"))

    def __repr__(self):
        return f"Expense({self._id}, {self._category}, {self._amount})"
