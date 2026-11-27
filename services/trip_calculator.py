"""Trip cost calculation. All formulas are documented in the README."""
import copy

from models.destination import Destination
from models.trip import CostBreakdown, Trip
from utils.calculations import emergency_allowance, rooms_required, round_pkr
from utils.constants import DEFAULT_SETTINGS, LOCAL_PAIRS
from utils.validators import ValidationError


class TripCostCalculator:
    def __init__(self, settings=None):
        self.settings = settings if settings is not None else copy.deepcopy(DEFAULT_SETTINGS)

    @property
    def emergency_percentage(self):
        return self.settings["emergency_percentage"]

    def _is_local(self, city, destination):
        return city == destination.name or frozenset({city, destination.name}) in LOCAL_PAIRS

    def resolve_preferences(self, destination: Destination, trip: Trip):
        """Return (transport, accommodation). Explicit choices must be offered by the
        destination; otherwise category defaults (with a fallback) are used."""
        if trip.category not in destination.travel_categories:
            raise ValidationError(f"{destination.name} does not offer the {trip.category} travel category.")
        defaults = self.settings["category_defaults"][trip.category]
        result = []
        for chosen, default, offered, label in (
            (trip.transport, defaults["transport"], destination.transport_modes, "transport"),
            (trip.accommodation, defaults["accommodation"], destination.accommodation_types, "accommodation"),
        ):
            if chosen:
                if chosen not in offered:
                    raise ValidationError(f"{destination.name} does not offer {label} '{chosen}'.")
                result.append(chosen)
            else:
                result.append(default if default in offered else offered[0])
        return tuple(result)

    def transport_price_pp(self, destination, trip, mode):
        if self._is_local(trip.departure_city, destination):
            factor = self.settings["local_travel_factor"]
        else:
            factor = self.settings["departure_city_factors"].get(trip.departure_city, 1.5)
        return round_pkr(destination.transport_cost_pp * self.settings["transport_multipliers"][mode] * factor)

    def calculate(self, destination: Destination, trip: Trip) -> CostBreakdown:
        transport, accommodation = self.resolve_preferences(destination, trip)
        cat_mult = self.settings["category_multipliers"][trip.category]
        rooms = rooms_required(trip.travellers, destination.room_capacity)

        transportation = self.transport_price_pp(destination, trip, transport) * trip.travellers
        room_rate = round_pkr(destination.accommodation_per_room_night
                              * self.settings["accommodation_multipliers"][accommodation])
        accommodation_cost = room_rate * rooms * trip.nights  # zero nights -> zero
        food = round_pkr(destination.food_pp_day * cat_mult) * trip.travellers * trip.days
        activities = round_pkr(destination.activities_pp_day * cat_mult) * trip.travellers * trip.days
        misc = round_pkr(destination.misc_pp_day * cat_mult) * trip.travellers * trip.days

        subtotal = transportation + accommodation_cost + food + activities + misc
        emergency = emergency_allowance(subtotal, self.emergency_percentage)
        total = subtotal + emergency
        return CostBreakdown(transport, accommodation, rooms, transportation, accommodation_cost,
                             food, activities, misc, subtotal, emergency, total,
                             round(total / trip.travellers, 2))
