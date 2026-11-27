"""ReportGenerator: builds report summaries and coordinates PDF creation."""
import uuid
from datetime import datetime

from pdf.pdf_generator import PDFGenerationError, PDFReportGenerator
from utils.calculations import format_pkr
from utils.constants import COST_DISCLAIMER


class ReportError(Exception):
    """Raised when a report cannot be produced."""


class ReportGenerator:
    def __init__(self, data_manager, developer, planner_settings=None):
        self.data_manager = data_manager
        self.developer = developer
        self.pdf = PDFReportGenerator(developer)
        self.emergency_percentage = (planner_settings or {}).get("emergency_percentage", 10)

    # ---- summaries ----
    def trip_summary(self, plan, destination, confirmed=True):
        b, t = plan.breakdown, plan.trip
        return {
            "destination": t.destination, "region": destination.region, "departure_city": t.departure_city,
            "travellers": t.travellers, "days": t.days, "nights": t.nights, "category": t.category,
            "transport": b.transport_mode, "accommodation": b.accommodation_type, "rooms": b.rooms,
            "transportation": b.transportation, "accommodation_cost": b.accommodation, "food": b.food,
            "activities": b.activities, "miscellaneous": b.miscellaneous, "subtotal": b.subtotal,
            "emergency": b.emergency, "emergency_percentage": self.emergency_percentage, "total": b.total,
            "cost_per_person": b.cost_per_person, "budget": t.budget,
            "difference": plan.feasibility.difference, "status": plan.status,
            "is_over": not plan.feasibility.is_feasible, "confirmed": confirmed,
            "disclaimer": COST_DISCLAIMER,
        }

    @staticmethod
    def budget_summary(budget):
        return budget.summary()

    def trip_text(self, summary):
        s = summary
        label = "Shortage" if s["is_over"] else "Remaining"
        return "\n".join([
            f"Trip: {s['destination']} from {s['departure_city']} | {s['travellers']} traveller(s) | "
            f"{s['days']} days / {s['nights']} nights | {s['category']}",
            f"  Transport ({s['transport']}):   {format_pkr(s['transportation'])}",
            f"  Accommodation ({s['accommodation']}, {s['rooms']} room(s)): {format_pkr(s['accommodation_cost'])}",
            f"  Food:                 {format_pkr(s['food'])}",
            f"  Activities:           {format_pkr(s['activities'])}",
            f"  Miscellaneous:        {format_pkr(s['miscellaneous'])}",
            f"  Emergency allowance:  {format_pkr(s['emergency'])}",
            f"  TOTAL ESTIMATE:       {format_pkr(s['total'])}  ({format_pkr(s['cost_per_person'])} per person)",
            f"  Budget: {format_pkr(s['budget'])} | {label}: {format_pkr(abs(s['difference']))} | Status: {s['status']}",
        ])

    # ---- ids and files ----
    @staticmethod
    def new_report_id(prefix):
        return f"{prefix}-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6].upper()}"

    def unique_path(self, report_id):
        """Return (report_id, path) for a file that does not exist yet."""
        folder = self.data_manager.ensure_reports_dir()
        candidate, counter = report_id, 1
        while (folder / f"{candidate}.pdf").exists():
            counter += 1
            candidate = f"{report_id}-{counter}"
        return candidate, folder / f"{candidate}.pdf"

    def _record(self, report_id, kind, title, path):
        reference = {"report_id": report_id, "type": kind, "title": title, "file": path.name,
                     "created": datetime.now().isoformat(timespec="seconds")}
        self.data_manager.add_report(reference)
        return reference

    # ---- PDF entry points ----
    def generate_trip_report(self, planner):
        plan = planner.confirmed
        if plan is None:
            raise ReportError("Confirm the trip plan before generating a PDF.")
        destination = planner.find_destination(plan.trip.destination)
        summary = self.trip_summary(plan, destination, confirmed=True)
        report_id, path = self.unique_path(self.new_report_id("TRIP"))
        try:
            self.pdf.generate_trip_pdf(summary, planner.itinerary(plan), report_id,
                                       datetime.now().strftime("%d %B %Y"), path)
        except PDFGenerationError as exc:
            raise ReportError(str(exc)) from exc
        return path, self._record(report_id, "trip", f"Trip to {plan.trip.destination}", path)

    def generate_budget_report(self, budget):
        if not budget.confirmed:
            raise ReportError("Confirm the monthly budget before generating a PDF.")
        report_id, path = self.unique_path(self.new_report_id("BUD"))
        try:
            self.pdf.generate_budget_pdf(self.budget_summary(budget), report_id,
                                         datetime.now().strftime("%d %B %Y"), path)
        except PDFGenerationError as exc:
            raise ReportError(str(exc)) from exc
        title = f"{budget.budget_type} budget {budget.month}"
        return path, self._record(report_id, "budget", title, path)
