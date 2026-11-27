import pytest
from dataclasses import replace

from services.trip_calculator import TripCostCalculator
from utils.calculations import ceil_div, emergency_allowance, format_pkr, rooms_required
from utils.validators import ValidationError


@pytest.fixture
def calc(settings):
    return TripCostCalculator(settings)


def test_full_breakdown_matches_hand_calculation(calc, destinations, base_trip):
    b = calc.calculate(destinations[0], base_trip)
    assert b.transportation == 3000            # 1000 x 3 travellers
    assert b.rooms == 2                        # ceil(3 / 2)
    assert b.accommodation == 16000            # 4000 x 2 rooms x 2 nights
    assert b.food == 4500                      # 500 x 3 x 3 days
    assert b.activities == 1800
    assert b.miscellaneous == 900
    assert b.subtotal == 26200
    assert b.emergency == 2620                 # 10%
    assert b.total == 28820
    assert b.cost_per_person == pytest.approx(9606.67)


@pytest.mark.parametrize("travellers,capacity,expected", [(1, 2, 1), (2, 2, 1), (3, 2, 2), (4, 3, 2), (7, 3, 3), (50, 4, 13)])
def test_rooms_required_uses_ceiling(travellers, capacity, expected):
    assert rooms_required(travellers, capacity) == expected


def test_zero_night_trip_has_zero_accommodation(calc, destinations, base_trip):
    b = calc.calculate(destinations[0], replace(base_trip, days=1, nights=0))
    assert b.accommodation == 0
    assert b.food == 1500  # still charged for the one day
    assert b.total == b.subtotal + b.emergency


def test_nights_and_days_are_separate(calc, destinations, base_trip):
    a = calc.calculate(destinations[0], replace(base_trip, days=4, nights=2))
    b = calc.calculate(destinations[0], replace(base_trip, days=4, nights=3))
    assert a.food == b.food                      # same days -> same food
    assert b.accommodation - a.accommodation == 4000 * 2  # one more night, 2 rooms


def test_multiple_rooms_scale_accommodation(calc, destinations, base_trip):
    one = calc.calculate(destinations[0], replace(base_trip, travellers=2))
    two = calc.calculate(destinations[0], replace(base_trip, travellers=3))
    assert one.rooms == 1 and two.rooms == 2
    assert two.accommodation == 2 * one.accommodation


def test_budget_category_uses_cheaper_defaults_and_multipliers(calc, destinations, base_trip):
    trip = replace(base_trip, travellers=2, days=2, nights=1, category="Budget")
    b = calc.calculate(destinations[0], trip)
    assert (b.transport_mode, b.accommodation_type) == ("Bus", "Guest House")
    assert b.transportation == 1200 and b.accommodation == 2000
    assert b.food == 1400 and b.activities == 560 and b.miscellaneous == 280
    assert b.total == 5984


def test_explicit_preferences_change_costs(calc, destinations, base_trip):
    resort = calc.calculate(destinations[0], replace(base_trip, accommodation="Resort"))
    hotel = calc.calculate(destinations[0], base_trip)
    assert resort.accommodation > hotel.accommodation
    assert resort.accommodation == round(4000 * 1.9) * 2 * 2


def test_departure_city_and_local_travel_factors(calc, destinations, base_trip):
    near = calc.calculate(destinations[0], base_trip).transportation
    far = calc.calculate(destinations[0], replace(base_trip, departure_city="Karachi")).transportation
    assert far == round(1000 * 2.2) * 3 and far > near
    local = calc.calculate(destinations[0], replace(base_trip, departure_city="Islamabad"))
    assert local.transportation == near


def test_unsupported_category_raises(calc, destinations, base_trip):
    with pytest.raises(ValidationError):
        calc.calculate(destinations[2], replace(base_trip, category="Budget"))  # Gamma is Premium-only


def test_emergency_percentage_is_configurable(destinations, settings, base_trip):
    settings["emergency_percentage"] = 0
    assert TripCostCalculator(settings).calculate(destinations[0], base_trip).emergency == 0
    settings["emergency_percentage"] = 20
    assert TripCostCalculator(settings).calculate(destinations[0], base_trip).emergency == 5240


@pytest.mark.parametrize("subtotal,pct,expected", [(1000, 10, 100), (1001, 10, 101), (0, 10, 0), (999, 5, 50)])
def test_emergency_allowance_rounds_up(subtotal, pct, expected):
    assert emergency_allowance(subtotal, pct) == expected


def test_helpers():
    assert ceil_div(7, 2) == 4
    with pytest.raises(ValueError):
        ceil_div(1, 0)
    assert format_pkr(1234567) == "PKR 1,234,567"
    assert format_pkr(-50) == "-PKR 50"
    assert format_pkr(10.5) == "PKR 10.50"
