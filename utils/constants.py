"""Shared constants and default calculation settings."""

MAX_TRAVELLERS = 50
MAX_DAYS = 30
MAX_AMOUNT = 1_000_000_000

TRAVEL_CATEGORIES = ("Budget", "Standard", "Premium")
DESTINATION_TYPES = ("Mountains", "Historical Places", "Lakes & Nature", "Any")
DESTINATION_CATEGORIES = DESTINATION_TYPES[:3]
TRANSPORT_MODES = ("Bus", "Car", "Flight")
ACCOMMODATION_TYPES = ("Guest House", "Hotel", "Resort")
DEPARTURE_CITIES = (
    "Islamabad", "Rawalpindi", "Lahore", "Karachi",
    "Peshawar", "Faisalabad", "Multan", "Quetta",
)
LOCAL_PAIRS = (frozenset({"Islamabad", "Rawalpindi"}),)

HOME_KITCHEN = "Home & Kitchen"
PERSONAL_FINANCE = "Personal Finance"

COST_DISCLAIMER = (
    "All costs are estimates based on typical prices and are NOT guaranteed "
    "market prices. Actual prices vary by season, availability and provider."
)

# Defaults used when destinations.json does not override them.
DEFAULT_SETTINGS = {
    "emergency_percentage": 10,
    "local_travel_factor": 0.15,
    "departure_city_factors": {
        "Islamabad": 1.0, "Rawalpindi": 1.0, "Peshawar": 1.1, "Lahore": 1.25,
        "Faisalabad": 1.35, "Multan": 1.6, "Quetta": 2.0, "Karachi": 2.2,
    },
    "transport_multipliers": {"Bus": 0.6, "Car": 1.0, "Flight": 2.4},
    "accommodation_multipliers": {"Guest House": 0.5, "Hotel": 1.0, "Resort": 1.9},
    "category_multipliers": {"Budget": 0.7, "Standard": 1.0, "Premium": 1.6},
    "category_defaults": {
        "Budget": {"transport": "Bus", "accommodation": "Guest House"},
        "Standard": {"transport": "Car", "accommodation": "Hotel"},
        "Premium": {"transport": "Car", "accommodation": "Resort"},
    },
}
