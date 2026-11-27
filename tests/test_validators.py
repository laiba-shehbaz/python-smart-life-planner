import pytest

from utils import validators as v
from utils.constants import MAX_DAYS, MAX_TRAVELLERS


@pytest.mark.parametrize("value", ["", "   ", "abc", "-5", "0", "12.5", None, True, 1e12, 0, -1])
def test_parse_budget_rejects_invalid(value):
    with pytest.raises(v.ValidationError):
        v.parse_budget(value)


@pytest.mark.parametrize("value,expected", [("150000", 150000), ("1,500,000", 1500000), (2500, 2500), ("PKR 900", 900), (" 7 ", 7)])
def test_parse_budget_accepts_valid(value, expected):
    assert v.parse_budget(value) == expected


@pytest.mark.parametrize("value", ["", "x", "0", "-2", "2.5", str(MAX_TRAVELLERS + 1)])
def test_parse_travellers_rejects_invalid(value):
    with pytest.raises(v.ValidationError):
        v.parse_travellers(value)


def test_traveller_limits_are_inclusive():
    assert v.parse_travellers("1") == 1
    assert v.parse_travellers(str(MAX_TRAVELLERS)) == MAX_TRAVELLERS


@pytest.mark.parametrize("value", ["", "zero", "0", "-1", str(MAX_DAYS + 1)])
def test_parse_days_rejects_invalid(value):
    with pytest.raises(v.ValidationError):
        v.parse_days(value)


@pytest.mark.parametrize("nights,days,ok", [("0", 1, True), ("2", 3, True), ("3", 3, True), ("4", 3, False), ("-1", 3, False), ("abc", 3, False)])
def test_parse_nights_against_days(nights, days, ok):
    if ok:
        assert v.parse_nights(nights, days) == int(nights)
    else:
        with pytest.raises(v.ValidationError):
            v.parse_nights(nights, days)


@pytest.mark.parametrize("value", ["", "abc", "-100", "nan", "inf", None])
def test_parse_amount_rejects_invalid(value):
    with pytest.raises(v.ValidationError):
        v.parse_amount(value)


def test_parse_amount_zero_rules_and_rounding():
    with pytest.raises(v.ValidationError):
        v.parse_amount("0")
    assert v.parse_amount("0", allow_zero=True) == 0
    assert v.parse_amount("10.456") == 10.46


@pytest.mark.parametrize("value,expected", [("1", "Mountains"), ("lakes & nature", "Lakes & Nature"), ("ANY", "Any")])
def test_parse_choice_accepts_index_and_case(value, expected):
    options = ("Mountains", "Historical Places", "Lakes & Nature", "Any")
    assert v.parse_choice(value, options, "Type") == (expected if not value.isdigit() else options[0])


def test_parse_choice_rejects_unknown_and_empty():
    with pytest.raises(v.ValidationError):
        v.parse_choice("Moon", ("A", "B"), "Thing")
    with pytest.raises(v.ValidationError):
        v.parse_choice("", ("A", "B"), "Thing")


@pytest.mark.parametrize("value", ["", "0", "9", "x", "-1", "1.5"])
def test_menu_choice_rejects_invalid_options(value):
    with pytest.raises(v.ValidationError):
        v.parse_menu_choice(value, 5)


def test_menu_choice_accepts_valid():
    assert v.parse_menu_choice(" 5 ", 5) == 5


@pytest.mark.parametrize("email,ok", [("a@b.com", True), ("first.last+tag@mail.example.pk", True),
                                      ("", False), ("no-at-sign.com", False), ("a@b", False), ("a b@c.com", False), (None, False)])
def test_validate_email(email, ok):
    if ok:
        assert v.validate_email(email) == email
    else:
        with pytest.raises(v.ValidationError):
            v.validate_email(email)


@pytest.mark.parametrize("value,ok", [("2026-11", True), ("2026-13", False), ("2026-00", False), ("26-11", False), ("", False), ("1999-05", False)])
def test_validate_month(value, ok):
    if ok:
        assert v.validate_month(value) == value
    else:
        with pytest.raises(v.ValidationError):
            v.validate_month(value)


@pytest.mark.parametrize("value", ["", "   ", "123abc", "bad@name", "x" * 41, None])
def test_invalid_custom_category_names(value):
    with pytest.raises(v.ValidationError):
        v.validate_category_name(value)


def test_category_name_whitespace_is_normalised():
    assert v.validate_category_name("  Pet   Care ") == "Pet Care"


@pytest.mark.parametrize("value,month", [("2026-02-30", None), ("hello", None), ("2026-10-05", "2026-11")])
def test_validate_date_rejects(value, month):
    with pytest.raises(v.ValidationError):
        v.validate_date(value, month)
