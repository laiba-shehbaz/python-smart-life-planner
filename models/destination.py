"""Destination model (immutable, validated)."""
from dataclasses import dataclass, asdict

from utils.constants import (ACCOMMODATION_TYPES, DESTINATION_CATEGORIES,
                             TRANSPORT_MODES, TRAVEL_CATEGORIES)
from utils.validators import ValidationError, parse_int

NUMERIC_FIELDS = ("transport_cost_pp", "accommodation_per_room_night", "food_pp_day",
                  "activities_pp_day", "misc_pp_day", "room_capacity")
LIST_FIELDS = {"travel_categories": TRAVEL_CATEGORIES, "transport_modes": TRANSPORT_MODES,
               "accommodation_types": ACCOMMODATION_TYPES}


@dataclass(frozen=True)
class Destination:
    name: str
    region: str
    category: str
    transport_cost_pp: int
    accommodation_per_room_night: int
    food_pp_day: int
    activities_pp_day: int
    misc_pp_day: int
    room_capacity: int
    travel_categories: tuple
    transport_modes: tuple
    accommodation_types: tuple
    highlights: tuple
    activities: tuple

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValidationError("Destination record must be an object.")
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValidationError("Destination record has no name.")
        prefix = f"Destination '{name}'"
        values = {"name": name}
        for key in ("region", "category"):
            text = str(data.get(key, "")).strip()
            if not text:
                raise ValidationError(f"{prefix}: missing field '{key}'.")
            values[key] = text
        if values["category"] not in DESTINATION_CATEGORIES:
            raise ValidationError(f"{prefix}: invalid category '{values['category']}'.")
        for key in NUMERIC_FIELDS:
            if key not in data:
                raise ValidationError(f"{prefix}: missing cost field '{key}'.")
            try:
                values[key] = parse_int(data[key], key, minimum=1 if key == "room_capacity" else 0,
                                        maximum=20 if key == "room_capacity" else 10_000_000)
            except ValidationError as exc:
                raise ValidationError(f"{prefix}: {exc}") from None
        for key, allowed in LIST_FIELDS.items():
            items = data.get(key)
            if not isinstance(items, (list, tuple)) or not items:
                raise ValidationError(f"{prefix}: '{key}' must be a non-empty list.")
            bad = [i for i in items if i not in allowed]
            if bad:
                raise ValidationError(f"{prefix}: invalid values in '{key}': {bad}.")
            values[key] = tuple(items)
        for key in ("highlights", "activities"):
            items = data.get(key) or ["Local sightseeing"]
            values[key] = tuple(str(i) for i in items)
        return cls(**values)

    def to_dict(self):
        return {k: list(v) if isinstance(v, tuple) else v for k, v in asdict(self).items()}
