import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.destination import Destination  # noqa: E402
from models.trip import Trip  # noqa: E402
from services.budget_manager import MonthlyBudgetManager  # noqa: E402
from services.report_generator import ReportGenerator  # noqa: E402
from services.trip_planner import TripPlanner  # noqa: E402
from utils.constants import DEFAULT_SETTINGS  # noqa: E402
from utils.data_manager import DataManager  # noqa: E402

import copy  # noqa: E402

ALL_CATS = ["Budget", "Standard", "Premium"]


def make_destination(name, transport, room, food, act, misc, cap, cats=None, category="Mountains"):
    return Destination.from_dict({
        "name": name, "region": "Test Region", "category": category,
        "transport_cost_pp": transport, "accommodation_per_room_night": room, "food_pp_day": food,
        "activities_pp_day": act, "misc_pp_day": misc, "room_capacity": cap,
        "travel_categories": cats or ALL_CATS, "transport_modes": ["Bus", "Car", "Flight"],
        "accommodation_types": ["Guest House", "Hotel", "Resort"],
        "highlights": ["Sight A", "Sight B"], "activities": ["Act A", "Act B"],
    })


@pytest.fixture
def destinations():
    return [
        make_destination("Alpha", 1000, 4000, 500, 200, 100, 2),
        make_destination("Beta", 3000, 8000, 800, 400, 200, 4),
        make_destination("Gamma", 500, 2000, 300, 100, 50, 2, cats=["Premium"], category="Historical Places"),
    ]


@pytest.fixture
def settings():
    return copy.deepcopy(DEFAULT_SETTINGS)


@pytest.fixture
def tmp_dm(tmp_path):
    return DataManager(tmp_path)


@pytest.fixture
def planner(destinations, settings, tmp_dm):
    return TripPlanner(destinations, settings, tmp_dm)


@pytest.fixture
def base_trip():
    """3 travellers, 3 days / 2 nights at Alpha -> total estimate PKR 28,820."""
    return Trip(budget=100000, travellers=3, destination="Alpha", departure_city="Islamabad",
                days=3, nights=2, category="Standard")


@pytest.fixture
def budget_manager(tmp_dm):
    return MonthlyBudgetManager(tmp_dm)


@pytest.fixture
def developer():
    return {"developer_name": "Test Dev", "github_username": "test-dev-gh", "email": "test.dev@example.com"}


@pytest.fixture
def reports(tmp_dm, developer, settings):
    return ReportGenerator(tmp_dm, developer, settings)
