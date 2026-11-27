"""Calculates (never hard-codes) alternatives for an over-budget trip.
Every alternative is fully recalculated and only kept if its total <= budget."""
from collections import namedtuple
from dataclasses import dataclass, field, replace
from typing import List, Optional

from models.trip import CostBreakdown, Trip
from utils.constants import MAX_TRAVELLERS
from utils.validators import ValidationError

AlternativePlan = namedtuple("AlternativePlan", "kind label trip breakdown score")
DestinationComparison = namedtuple("DestinationComparison", "name category total affordable difference")

WEIGHTS = {"destination": 0.25, "travellers": 0.25, "days": 0.20, "remaining": 0.15, "preferences": 0.15}


@dataclass
class OptimizationReport:
    trip: Trip
    breakdown: CostBreakdown
    shortage: int
    minimum_budget: int
    additional_budget: int
    max_travellers: int
    traveller_option: Optional[AlternativePlan] = None
    duration_options: List[AlternativePlan] = field(default_factory=list)
    destination_options: List[AlternativePlan] = field(default_factory=list)
    preference_options: List[AlternativePlan] = field(default_factory=list)
    ranked: List[AlternativePlan] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


class TripOptimizer:
    def __init__(self, calculator, destinations):
        """destinations: dict mapping destination name -> Destination."""
        self.calculator = calculator
        self.destinations = destinations

    def _cost(self, trip) -> Optional[CostBreakdown]:
        dest = self.destinations.get(trip.destination)
        if dest is None:
            return None
        try:
            return self.calculator.calculate(dest, trip)
        except ValidationError:
            return None

    # 1. increase budget
    def minimum_budget(self, trip):
        breakdown = self._cost(trip)
        if breakdown is None:
            raise ValidationError(f"Cannot cost destination '{trip.destination}'.")
        return breakdown.total, max(0, breakdown.total - trip.budget)

    # 2. reduce travellers
    def max_affordable_travellers(self, trip):
        for n in range(MAX_TRAVELLERS, 0, -1):
            cost = self._cost(replace(trip, travellers=n))
            if cost is not None and cost.total <= trip.budget:
                return n
        return 0

    # 3. reduce duration
    def feasible_durations(self, trip):
        found = []
        for days in range(trip.days, 0, -1):
            for nights in range(min(trip.nights, days), -1, -1):
                cost = self._cost(replace(trip, days=days, nights=nights))
                if cost is not None and cost.total <= trip.budget:
                    found.append((days, nights, cost.total))
                    break
        return found

    # 4. change destination
    def compare_destinations(self, trip):
        rows = []
        for name, dest in self.destinations.items():
            if trip.destination_type not in ("Any", dest.category):
                continue
            cost = self._cost(replace(trip, destination=name))
            if cost is None:
                continue
            rows.append(DestinationComparison(name, dest.category, cost.total,
                                              cost.total <= trip.budget, trip.budget - cost.total))
        return sorted(rows, key=lambda r: (r.total, r.name))

    # scoring / ranking
    def score(self, original, original_cost, new_trip, new_cost):
        orig_dest = self.destinations[original.destination]
        new_dest = self.destinations[new_trip.destination]
        if new_trip.destination == original.destination:
            dest_score = 1.0
        elif new_dest.category == orig_dest.category:
            dest_score = 0.6
        else:
            dest_score = 0.3
        same = ((new_cost.transport_mode == original_cost.transport_mode)
                + (new_cost.accommodation_type == original_cost.accommodation_type))
        parts = {
            "destination": dest_score,
            "travellers": min(1.0, new_trip.travellers / original.travellers),
            "days": min(1.0, new_trip.days / original.days),
            "remaining": max(0.0, min(1.0, (original.budget - new_cost.total) / original.budget)),
            "preferences": same / 2,
        }
        return round(sum(WEIGHTS[k] * v for k, v in parts.items()), 4)

    def _make(self, kind, label, original, original_cost, new_trip, new_cost):
        if new_cost is None or new_cost.total > original.budget:
            return None
        return AlternativePlan(kind, label, new_trip, new_cost,
                               self.score(original, original_cost, new_trip, new_cost))

    def rank(self, plans):
        return sorted(plans, key=lambda p: (-p.score, p.breakdown.total, p.label))

    def analyse(self, trip) -> OptimizationReport:
        if trip.destination not in self.destinations:
            raise ValidationError(f"Unknown destination '{trip.destination}'.")
        cost = self._cost(trip)
        if cost is None:
            raise ValidationError(f"{trip.destination} cannot be costed with the selected options.")
        required, additional = self.minimum_budget(trip)
        report = OptimizationReport(trip, cost, max(0, cost.total - trip.budget), required,
                                    additional, self.max_affordable_travellers(trip))
        if cost.total <= trip.budget:
            return report

        if 1 <= report.max_travellers < trip.travellers:
            n = report.max_travellers
            t = replace(trip, travellers=n)
            report.traveller_option = self._make("travellers", f"Reduce travellers to {n}", trip, cost, t, self._cost(t))
        for days, nights, _ in self.feasible_durations(trip):
            if (days, nights) == (trip.days, trip.nights):
                continue
            t = replace(trip, days=days, nights=nights)
            plan = self._make("duration", f"Shorten trip to {days} day{'s' if days != 1 else ''} / {nights} night{'s' if nights != 1 else ''}", trip, cost, t, self._cost(t))
            if plan:
                report.duration_options.append(plan)
        for row in self.compare_destinations(trip):
            if row.name == trip.destination or not row.affordable:
                continue
            t = replace(trip, destination=row.name)
            plan = self._make("destination", f"Change destination to {row.name}", trip, cost, t, self._cost(t))
            if plan:
                report.destination_options.append(plan)
        dest = self.destinations[trip.destination]
        for transport in dest.transport_modes:
            for accommodation in dest.accommodation_types:
                if (transport, accommodation) == (cost.transport_mode, cost.accommodation_type):
                    continue
                t = replace(trip, transport=transport, accommodation=accommodation)
                plan = self._make("preferences", f"Use {transport} + {accommodation}", trip, cost, t, self._cost(t))
                if plan:
                    report.preference_options.append(plan)
        report.ranked = self.rank([p for p in [report.traveller_option] if p] + report.duration_options
                                  + report.destination_options + report.preference_options)

        if report.max_travellers == 0:
            report.notes.append("The budget cannot cover even one traveller for this trip.")
        if not report.duration_options:
            report.notes.append("Even the shortest practical trip (1 day) is unaffordable with these settings.")
        if not report.destination_options:
            report.notes.append("No other destination is affordable within the budget with your constraints.")
        if not report.ranked:
            report.notes.append(f"No alternative fits the budget; the minimum required budget is PKR {required:,}.")
        return report
