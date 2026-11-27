"""TripPlanner: evaluates, modifies, confirms and cancels trip plans."""
from collections import deque, namedtuple
from dataclasses import replace
from itertools import cycle

from models.trip import Trip, TripPlan
from services.feasibility_checker import TripFeasibilityChecker
from services.trip_calculator import TripCostCalculator
from services.trip_optimizer import TripOptimizer
from utils.validators import ValidationError

ItineraryDay = namedtuple("ItineraryDay", "day title items")
MODIFIABLE = ("budget", "travellers", "destination", "departure_city", "days", "nights",
              "category", "transport", "accommodation", "destination_type")


def build_itinerary(destination, trip, transport, accommodation, rooms):
    """Day-by-day plan adapted to the real number of days and nights."""
    highlights, activities = cycle(destination.highlights), cycle(destination.activities)
    city, name = trip.departure_city, destination.name
    days = []
    for d in range(1, trip.days + 1):
        items = []
        if trip.days == 1:
            title = f"Day trip to {name}"
        elif d == 1:
            title = "Departure and arrival"
        elif d == trip.days:
            title = "Final sightseeing and return"
        else:
            title = "Sightseeing and activities"
        if d == 1:
            items.append(f"Depart from {city} by {transport}.")
            items.append(f"Arrive in {name} ({destination.region}).")
            if trip.nights >= 1:
                items.append(f"Check in to {accommodation} ({rooms} room{'s' if rooms != 1 else ''}).")
        items.append(f"Sightseeing: {next(highlights)}.")
        items.append(f"Activity: {next(activities)}.")
        if d == trip.days and d <= trip.nights:
            items.append(f"Overnight stay at {accommodation}; check out and return to {city} by {transport} next morning.")
        elif d == trip.days:
            items.append(f"Return journey to {city} by {transport}.")
        elif d <= trip.nights:
            items.append(f"Overnight stay at {accommodation}.")
        else:
            items.append("Day-use only (no overnight accommodation is included on this day).")
        days.append(ItineraryDay(d, title, items))
    return days


class TripPlanner:
    def __init__(self, destinations, settings=None, data_manager=None):
        self.destinations = {d.name: d for d in destinations}
        self.calculator = TripCostCalculator(settings)
        self.checker = TripFeasibilityChecker()
        self.optimizer = TripOptimizer(self.calculator, self.destinations)
        self.data_manager = data_manager
        self._confirmed = None
        self._pending = None
        self.history = deque(maxlen=10)
        self.last_record = None

    @property
    def confirmed(self):
        return self._confirmed

    @property
    def pending(self):
        return self._pending

    @property
    def current(self):
        return self._pending or self._confirmed

    def find_destination(self, name):
        wanted = str(name).strip().lower()
        for dest in self.destinations.values():
            if dest.name.lower() == wanted:
                return dest
        raise ValidationError(f"Unknown destination '{name}'. Available: {', '.join(self.destinations)}.")

    def evaluate(self, trip) -> TripPlan:
        """Pure calculation: does not change planner state."""
        dest = self.find_destination(trip.destination)
        if dest.name != trip.destination:
            trip = replace(trip, destination=dest.name)
        breakdown = self.calculator.calculate(dest, trip)
        return TripPlan(trip, breakdown, self.checker.check(breakdown, trip.budget))

    def propose(self, trip):
        plan = self.evaluate(trip)
        self._pending = plan
        self.history.append(f"Proposed {plan.trip.destination} ({plan.status})")
        return plan

    def modify(self, **changes):
        base = self.current
        if base is None:
            raise ValidationError("There is no plan to modify. Create a plan first.")
        unknown = set(changes) - set(MODIFIABLE)
        if unknown:
            raise ValidationError(f"Cannot modify: {', '.join(sorted(unknown))}.")
        if not changes:
            raise ValidationError("No changes were given.")
        plan = self.evaluate(replace(base.trip, **changes))  # validated + fully recalculated
        self._pending = plan
        self.history.append("Modified " + ", ".join(sorted(changes)))
        return plan

    def confirm(self):
        if self._pending is None:
            raise ValidationError("There are no pending changes to confirm.")
        plan = self._pending
        if self.data_manager is not None:
            record = self.data_manager.save_trip(plan.to_dict())  # raises before state changes
            self.last_record = record
        self._confirmed, self._pending = plan, None
        self.history.append(f"Confirmed {plan.trip.destination}")
        return plan

    def cancel(self):
        had_pending = self._pending is not None
        self._pending = None
        if had_pending:
            self.history.append("Cancelled pending changes")
        return had_pending

    def itinerary(self, plan=None):
        plan = plan or self.current
        if plan is None:
            raise ValidationError("No plan available for an itinerary.")
        dest = self.find_destination(plan.trip.destination)
        b = plan.breakdown
        return build_itinerary(dest, plan.trip, b.transport_mode, b.accommodation_type, b.rooms)

    def optimize(self, plan=None):
        plan = plan or self.current
        if plan is None:
            raise ValidationError("No plan to optimise.")
        return self.optimizer.analyse(plan.trip)

    @staticmethod
    def diff(old, new):
        """Fields that changed between two plans, as {name: (old, new)}."""
        changes = {}
        for key, value in new.trip.to_dict().items():
            if old.trip.to_dict()[key] != value:
                changes[key] = (old.trip.to_dict()[key], value)
        for key in ("rooms", "transportation", "accommodation", "food", "activities",
                    "miscellaneous", "emergency", "total", "cost_per_person"):
            if getattr(old.breakdown, key) != getattr(new.breakdown, key):
                changes[key] = (getattr(old.breakdown, key), getattr(new.breakdown, key))
        if old.status != new.status:
            changes["status"] = (old.status, new.status)
        return changes
