"""Input validation helpers. Every function raises ValidationError with a
human-readable message and never returns bad data."""
import math
import re
from datetime import date

from utils.constants import MAX_AMOUNT, MAX_DAYS, MAX_TRAVELLERS

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
CATEGORY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 &/'\-]*$")
EXPENSE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,20}$")
MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


class ValidationError(ValueError):
    """Raised when user or file input is invalid."""


def parse_int(value, label, minimum=None, maximum=None):
    if isinstance(value, bool):
        raise ValidationError(f"{label} must be a whole number.")
    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValidationError(f"{label} must be a whole number.")
        number = int(value)
    elif isinstance(value, str):
        text = re.sub(r"(?i)^pkr\s*", "", value.strip()).replace(",", "")
        if not text:
            raise ValidationError(f"{label} cannot be empty.")
        try:
            number = int(text)
        except ValueError:
            raise ValidationError(f"{label} must be a whole number (got '{value.strip()}').") from None
    else:
        raise ValidationError(f"{label} must be a whole number.")
    if minimum is not None and number < minimum:
        raise ValidationError(f"{label} must be at least {minimum} (got {number}).")
    if maximum is not None and number > maximum:
        raise ValidationError(f"{label} must be at most {maximum:,} (got {number:,}).")
    return number


def parse_amount(value, label="Amount", allow_zero=False, maximum=MAX_AMOUNT):
    """Parse a PKR amount (up to 2 decimals). Rejects NaN/inf/negative values."""
    if isinstance(value, bool):
        raise ValidationError(f"{label} must be a number.")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = re.sub(r"(?i)^pkr\s*", "", value.strip()).replace(",", "")
        if not text:
            raise ValidationError(f"{label} cannot be empty.")
        try:
            number = float(text)
        except ValueError:
            raise ValidationError(f"{label} must be a number (got '{value.strip()}').") from None
    else:
        raise ValidationError(f"{label} must be a number.")
    if not math.isfinite(number):
        raise ValidationError(f"{label} must be a finite number.")
    if number < 0:
        raise ValidationError(f"{label} cannot be negative.")
    if number == 0 and not allow_zero:
        raise ValidationError(f"{label} must be greater than zero.")
    if number > maximum:
        raise ValidationError(f"{label} is too large (maximum {maximum:,}).")
    return round(number, 2)


def parse_budget(value):
    return parse_int(value, "Budget", minimum=1, maximum=MAX_AMOUNT)


def parse_travellers(value):
    return parse_int(value, "Number of travellers", minimum=1, maximum=MAX_TRAVELLERS)


def parse_days(value):
    return parse_int(value, "Number of days", minimum=1, maximum=MAX_DAYS)


def parse_nights(value, days=None):
    nights = parse_int(value, "Number of nights", minimum=0, maximum=MAX_DAYS)
    if days is not None and nights > days:
        raise ValidationError(f"Nights ({nights}) cannot be greater than days ({days}).")
    return nights


def parse_choice(value, options, label):
    """Match text (or a 1-based index) against options, case-insensitively."""
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValidationError(f"{label} cannot be empty.")
    if text.isdigit() and 1 <= int(text) <= len(options):
        return options[int(text) - 1]
    for option in options:
        if option.lower() == text.lower():
            return option
    raise ValidationError(f"Invalid {label.lower()} '{text}'. Choose from: {', '.join(options)}.")


def parse_menu_choice(value, count):
    text = str(value).strip()
    if not text.isdigit() or not 1 <= int(text) <= count:
        raise ValidationError(f"Invalid option '{text}'. Enter a number from 1 to {count}.")
    return int(text)


def validate_email(email):
    if not isinstance(email, str) or not EMAIL_RE.match(email.strip()):
        raise ValidationError(f"Invalid email address: {email!r}.")
    return email.strip()


def validate_month(value):
    text = str(value).strip()
    match = MONTH_RE.match(text)
    if not match or not 2000 <= int(match.group(1)) <= 2100:
        raise ValidationError("Budget month must look like YYYY-MM (for example 2026-11).")
    return text


def validate_date(value, month=None):
    text = str(value).strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        raise ValidationError(f"Invalid date '{text}'. Use YYYY-MM-DD.") from None
    if month and not text.startswith(month):
        raise ValidationError(f"Date {text} is outside the budget month {month}.")
    return parsed.isoformat()


def validate_category_name(value):
    text = re.sub(r"\s+", " ", str(value).strip()) if value is not None else ""
    if not text:
        raise ValidationError("Category name cannot be empty.")
    if len(text) > 40:
        raise ValidationError("Category name must be at most 40 characters.")
    if not CATEGORY_RE.match(text):
        raise ValidationError("Category name must start with a letter and use only letters, digits, spaces, & / ' -.")
    return text


def validate_expense_id(value):
    text = str(value).strip() if value is not None else ""
    if not EXPENSE_ID_RE.match(text):
        raise ValidationError("Expense ID must be 1-20 characters: letters, digits, '_' or '-'.")
    return text


def validate_description(value):
    text = str(value).strip() if value is not None else ""
    if len(text) > 100:
        raise ValidationError("Description must be at most 100 characters.")
    return text or "No description"
