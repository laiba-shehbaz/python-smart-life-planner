"""Trip request and plan models."""
from collections import namedtuple
from dataclasses import dataclass, asdict
from typing import Any, Optional

from utils.constants import (ACCOMMODATION_TYPES, DEPARTURE_CITIES, DESTINATION_TYPES,
                             TRANSPORT_MODES, TRAVEL_CATEGORIES)
from utils.validators import (ValidationError, parse_budget, parse_choice, parse_days,
                              parse_nights, parse_travellers)

CostBreakdown = namedtuple(
    "CostBreakdown",
    "transport_mode accommodation_type rooms transportation accommodation food "
    "activities miscellaneous subtotal emergency total cost_per_person",
)


def _optional_choice(value, options, label):
    if value is None or str(value).strip().lower() in ("", "auto", "none"):
        return None
    return parse_choice(value, options, label)


@dataclass(frozen=True)
class Trip:
    """A validated trip request. Invalid values raise ValidationError."""
    budget: int
    travellers: int
    destination: str
    departure_city: str
    days: int
    nights: int
    category: str = "Standard"
    transport: Optional[str] = None
    accommodation: Optional[str] = None
    destination_type: str = "Any"

    def __post_init__(self):
        def put(name, value):
            object.__setattr__(self, name, value)
        put("budget", parse_budget(self.budget))
        put("travellers", parse_travellers(self.travellers))
        destination = str(self.destination or "").strip()
        if not destination:
            raise ValidationError("Destination cannot be empty (use 'Any' to get suggestions).")
        put("destination", destination)
        put("departure_city", parse_choice(self.departure_city, DEPARTURE_CITIES, "Departure city"))
        days = parse_days(self.days)
        put("days", days)
        put("nights", parse_nights(self.nights, days))
        put("category", parse_choice(self.category, TRAVEL_CATEGORIES, "Travel category"))
        put("transport", _optional_choice(self.transport, TRANSPORT_MODES, "Transport"))
        put("accommodation", _optional_choice(self.accommodation, ACCOMMODATION_TYPES, "Accommodation"))
        put("destination_type", parse_choice(self.destination_type, DESTINATION_TYPES, "Destination type"))

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValidationError("Trip record must be an object.")
        allowed = cls.__dataclass_fields__.keys()
        try:
            return cls(**{k: v for k, v in data.items() if k in allowed})
        except TypeError as exc:
            raise ValidationError(f"Trip record is incomplete: {exc}") from None


@dataclass(frozen=True)
class TripPlan:
    """A trip together with its calculated costs and feasibility."""
    trip: Trip
    breakdown: CostBreakdown
    feasibility: Any

    @property
    def total(self):
        return self.breakdown.total

    @property
    def status(self):
        return self.feasibility.status

    def to_dict(self):
        return {"trip": self.trip.to_dict(), "breakdown": self.breakdown._asdict(),
                "feasibility": self.feasibility._asdict()}
