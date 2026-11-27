"""Smart Life Planner - menu-driven entry point."""
import sys

from models.trip import Trip
from services.budget_manager import MonthlyBudgetManager
from services.report_generator import ReportError, ReportGenerator
from services.trip_planner import TripPlanner
from pdf.pdf_generator import PDFGenerationError
from utils import validators as v
from utils.calculations import format_pkr
from utils.constants import (ACCOMMODATION_TYPES, COST_DISCLAIMER, DEPARTURE_CITIES,
                             DESTINATION_TYPES, TRANSPORT_MODES, TRAVEL_CATEGORIES)
from utils.data_manager import DataError, DataManager

HANDLED = (v.ValidationError, DataError, ReportError, PDFGenerationError)


class SmartLifePlanner:
    def __init__(self, data_manager=None, input_fn=input, output_fn=print):
        self.dm = data_manager or DataManager()
        self.input_fn, self.out = input_fn, output_fn
        data = self.dm.load_destination_data()
        for message in data.errors:
            self.out(f"[Warning] {message}")
        self.planner = TripPlanner(data.destinations, data.settings, self.dm)
        self.budgets = MonthlyBudgetManager(self.dm)
        self.budgets.load()
        self.developer = self.dm.load_developer()
        self.reports = ReportGenerator(self.dm, self.developer, data.settings)
        self.active_budget = None
        for message in self.dm.warnings + self.budgets.load_errors:
            self.out(f"[Warning] {message}")

    # ---------- input helpers ----------
    def ask(self, label, parser, default=None):
        while True:
            raw = self.input_fn(f"{label}: ").strip()
            if raw == "" and default is not None:
                raw = str(default)
            try:
                return parser(raw)
            except v.ValidationError as exc:
                self.out(f"  ! {exc}")

    def ask_choice(self, label, options, default=None):
        self.out(f"{label}: " + ", ".join(f"{i}) {o}" for i, o in enumerate(options, 1)))
        return self.ask("  Your choice", lambda r: v.parse_choice(r, options, label), default)

    def yes_no(self, question):
        return self.input_fn(f"{question} (y/n): ").strip().lower() in ("y", "yes")

    def menu(self, title, options):
        while True:
            self.out(f"\n=== {title} ===")
            for i, text in enumerate(options, 1):
                self.out(f"  {i}. {text}")
            raw = self.input_fn("Select an option: ")
            try:
                return v.parse_menu_choice(raw, len(options))
            except v.ValidationError as exc:
                self.out(f"  ! {exc}")

    def guarded(self, action):
        try:
            action()
        except HANDLED as exc:
            self.out(f"  ! {exc}")

    # ---------- main loop ----------
    def run(self):
        self.out("Welcome to Smart Life Planner!")
        try:
            while True:
                choice = self.menu("Main Menu", ["Pakistan Trip Planner", "Monthly Budget Manager",
                                                 "View Previous Reports", "Developer Information", "Exit"])
                if choice == 1:
                    self.trip_menu()
                elif choice == 2:
                    self.budget_menu()
                elif choice == 3:
                    self.guarded(self.show_previous)
                elif choice == 4:
                    self.show_developer()
                else:
                    if self.planner.pending and not self.yes_no("You have unconfirmed trip changes that will be lost. Exit anyway?"):
                        continue
                    self.out("Goodbye!")
                    return
        except (EOFError, KeyboardInterrupt):
            self.out("\nInput closed. Goodbye!")

    # ---------- trip module ----------
    def trip_menu(self):
        actions = {1: self.new_trip, 2: self.show_trip, 3: self.show_alternatives, 4: self.modify_trip,
                   5: self.confirm_trip, 6: self.cancel_trip, 7: self.trip_pdf, 8: self.saved_trips}
        labels = ["Plan a new trip", "View current plan & itinerary", "Show feasibility alternatives",
                  "Modify plan", "Confirm plan (save)", "Cancel pending changes", "Generate trip PDF",
                  "View saved trips", "Back to main menu"]
        while True:
            choice = self.menu("Pakistan Trip Planner", labels)
            if choice == 9:
                return
            self.guarded(actions[choice])

    def new_trip(self):
        self.out("Note: " + COST_DISCLAIMER)
        budget = self.ask("Available budget (PKR)", v.parse_budget)
        travellers = self.ask("Number of travellers", v.parse_travellers)
        city = self.ask_choice("Departure city", DEPARTURE_CITIES)
        dtype = self.ask_choice("Destination type", DESTINATION_TYPES, default="Any")
        names = list(self.planner.destinations)
        self.out("Destinations: " + ", ".join(names) + " (or type Any for suggestions)")
        destination = self.input_fn("Destination: ").strip() or "Any"
        days = self.ask("Number of days", v.parse_days)
        nights = self.ask("Number of nights (0 allowed)", lambda r: v.parse_nights(r, days))
        category = self.ask_choice("Travel category", TRAVEL_CATEGORIES, default="Standard")
        transport = self.input_fn(f"Transport preference ({'/'.join(TRANSPORT_MODES)}/auto) [auto]: ").strip() or None
        stay = self.input_fn(f"Accommodation preference ({'/'.join(ACCOMMODATION_TYPES)}/auto) [auto]: ").strip() or None
        trip = Trip(budget, travellers, destination, city, days, nights, category, transport, stay, dtype)
        if destination.lower() == "any":
            rows = self.planner.optimizer.compare_destinations(trip)
            if not rows:
                self.out("No destination matches your preferences.")
                return
            for i, row in enumerate(rows, 1):
                mark = "affordable" if row.affordable else "over budget"
                self.out(f"  {i}. {row.name:<11} {format_pkr(row.total):>14}  [{mark}]")
            pick = self.ask("Pick a destination number", lambda r: v.parse_menu_choice(r, len(rows)))
            trip = Trip(**{**trip.to_dict(), "destination": rows[pick - 1].name})
        self.display_plan(self.planner.propose(trip))
        self.out("Plan is PENDING. Use 'Confirm plan' to save it.")

    def display_plan(self, plan):
        dest = self.planner.find_destination(plan.trip.destination)
        self.out(self.reports.trip_text(self.reports.trip_summary(plan, dest, confirmed=False)))
        self.out("  " + self.planner.checker.explain(plan.feasibility))

    def show_trip(self):
        plan = self.planner.current
        if plan is None:
            raise v.ValidationError("No trip plan yet. Plan a new trip first.")
        self.out("Status: " + ("PENDING (unconfirmed)" if self.planner.pending else "CONFIRMED"))
        self.display_plan(plan)
        for day in self.planner.itinerary(plan):
            self.out(f"\n  Day {day.day}: {day.title}")
            for item in day.items:
                self.out(f"    - {item}")

    def show_alternatives(self):
        plan = self.planner.current
        if plan is None:
            raise v.ValidationError("No trip plan yet. Plan a new trip first.")
        report = self.planner.optimize(plan)
        self.display_plan(plan)
        if plan.feasibility.is_feasible:
            self.out("This plan fits the budget; no alternatives are needed.")
            return
        self.out(f"\nShortage: {format_pkr(report.shortage)}")
        self.out(f"1. Increase budget: need {format_pkr(report.minimum_budget)} (add {format_pkr(report.additional_budget)}).")
        self.out(f"2. Reduce travellers: max {report.max_travellers} can travel within budget." if report.max_travellers
                 else "2. Reduce travellers: budget cannot cover even one traveller.")
        for label, opts in (("3. Reduce duration", report.duration_options),
                            ("4. Change destination", report.destination_options),
                            ("5. Adjust preferences", report.preference_options)):
            self.out(label + ":" + ("" if opts else " none affordable"))
            for o in opts[:4]:
                self.out(f"     {o.label}: {format_pkr(o.breakdown.total)}")
        self.out("6. Best alternatives (ranked):")
        for i, o in enumerate(report.ranked[:5], 1):
            self.out(f"     {i}. {o.label} - {format_pkr(o.breakdown.total)} (score {o.score})")
        for note in report.notes:
            self.out("  Note: " + note)

    def modify_trip(self):
        if self.planner.current is None:
            raise v.ValidationError("No trip plan yet. Plan a new trip first.")
        old = self.planner.current
        self.out("Fields: budget, travellers, destination, departure_city, days, nights, category, transport, accommodation")
        changes = {}
        while True:
            field = self.input_fn("Field to change (blank when done): ").strip().lower()
            if not field:
                break
            changes[field] = self.input_fn(f"New value for {field}: ").strip()
        if not changes:
            self.out("No changes entered.")
            return
        new = self.planner.modify(**changes)
        self.out("Proposed changes:")
        for key, (before, after) in self.planner.diff(old, new).items():
            self.out(f"  {key}: {before} -> {after}")
        self.display_plan(new)
        if self.yes_no("Confirm these changes?"):
            self.planner.confirm()
            self.out("Changes confirmed and saved.")
        else:
            self.planner.cancel()
            self.out("Changes cancelled; previous confirmed plan kept.")

    def confirm_trip(self):
        self.planner.confirm()
        self.out("Plan confirmed and saved.")

    def cancel_trip(self):
        self.out("Pending changes discarded." if self.planner.cancel() else "Nothing to cancel.")

    def trip_pdf(self):
        path, ref = self.reports.generate_trip_report(self.planner)
        self.out(f"PDF created: {path}")

    def saved_trips(self):
        trips = self.dm.load_trips()
        if not trips:
            self.out("No saved trips yet.")
        for t in trips:
            tr, br = t["trip"], t["breakdown"]
            self.out(f"  {t['plan_id']}: {tr.get('destination')} | {tr.get('travellers')} pax | "
                     f"{tr.get('days')}d/{tr.get('nights')}n | {format_pkr(br['total'])}")

    # ---------- budget module ----------
    def budget_menu(self):
        actions = {1: self.create_budget, 2: self.select_budget, 3: self.add_category, 4: self.update_category,
                   5: self.remove_category, 6: self.set_planned, 7: self.add_expense, 8: self.update_expense,
                   9: self.delete_expense, 10: self.view_expenses, 11: self.view_category, 12: self.budget_summary,
                   13: self.confirm_budget, 14: self.budget_pdf}
        labels = ["Create monthly budget", "Select existing budget", "Add category", "Update/rename category",
                  "Remove category", "Set planned amount", "Record expense", "Update expense", "Delete expense",
                  "View all expenses", "View category-wise records", "Summary (totals, savings, overspending)",
                  "Confirm budget", "Generate budget PDF", "Back to main menu"]
        while True:
            choice = self.menu("Monthly Budget Manager" + (f" [{self.active_budget.budget_type} {self.active_budget.month}]" if self.active_budget else ""), labels)
            if choice == 15:
                return
            if choice > 2 and self.active_budget is None:
                self.out("  ! Create or select a budget first.")
                continue
            self.guarded(actions[choice])
            if choice in range(3, 10):
                self.guarded(self.budgets.save)

    def create_budget(self):
        month = self.ask("Budget month (YYYY-MM)", v.validate_month)
        total = self.ask("Total monthly available amount (PKR)", v.parse_amount)
        btype = self.ask_choice("Budget type", self.budgets.budget_types())
        self.active_budget = self.budgets.create_budget(month, total, btype)
        self.out(f"Created {btype} budget for {month} with categories: " + ", ".join(self.active_budget.categories))

    def select_budget(self):
        items = self.budgets.list_budgets()
        if not items:
            raise v.ValidationError("No saved budgets. Create one first.")
        for i, b in enumerate(items, 1):
            self.out(f"  {i}. {b.budget_type} {b.month} ({format_pkr(b.total_amount)})")
        self.active_budget = items[self.ask("Select budget", lambda r: v.parse_menu_choice(r, len(items))) - 1]

    def add_category(self):
        name = self.ask("New category name", v.validate_category_name)
        planned = self.ask("Planned amount (0 allowed)", lambda r: v.parse_amount(r, "Planned amount", allow_zero=True), default=0)
        self.active_budget.add_category(name, planned)
        self.out("Category added.")

    def update_category(self):
        old = self.input_fn("Category to update: ").strip()
        new = self.input_fn("New name (blank to keep): ").strip()
        if new:
            self.active_budget.rename_category(old, new)
        amount = self.input_fn("New planned amount (blank to keep): ").strip()
        if amount:
            self.active_budget.set_planned(new or old, amount)
        self.out("Category updated.")

    def remove_category(self):
        self.active_budget.remove_category(self.input_fn("Category to remove: "))
        self.out("Category removed.")

    def set_planned(self):
        name = self.input_fn("Category: ")
        self.active_budget.set_planned(name, self.input_fn("Planned amount (PKR): "))
        b = self.active_budget
        if b.is_over_allocated:
            self.out(f"  Warning: planned total {format_pkr(b.total_planned)} exceeds budget {format_pkr(b.total_amount)}.")
        self.out("Planned amount set.")

    def add_expense(self):
        b = self.active_budget
        self.out("Categories: " + ", ".join(b.categories))
        category = self.input_fn("Category: ")
        amount = self.input_fn("Amount (PKR): ")
        description = self.input_fn("Description: ")
        day = self.input_fn(f"Date YYYY-MM-DD [{b.month}-01]: ").strip() or None
        exp_id = self.input_fn("Expense ID (blank = automatic): ").strip() or None
        expense = b.add_expense(category, amount, description, day, exp_id)
        self.budgets.log(f"Added expense {expense.expense_id}")
        self.out(f"Recorded {expense.expense_id}: {expense.category} {format_pkr(expense.amount)}")
        if b.is_overspent:
            self.out("  Warning: total spending now exceeds the monthly budget!")
        elif any(r.category == expense.category for r in b.overspent_categories()):
            self.out(f"  Warning: {expense.category} is over its planned amount.")

    def update_expense(self):
        exp_id = self.input_fn("Expense ID: ")
        fields = {}
        for key, label in (("category", "Category"), ("amount", "Amount"), ("description", "Description"), ("expense_date", "Date")):
            value = self.input_fn(f"New {label} (blank to keep): ").strip()
            if value:
                fields[key] = value
        self.active_budget.update_expense(exp_id, **fields)
        self.out("Expense updated.")

    def delete_expense(self):
        self.active_budget.delete_expense(self.input_fn("Expense ID to delete: "))
        self.out("Expense deleted.")

    def view_expenses(self):
        items = self.active_budget.expenses
        if not items:
            self.out("No expenses recorded yet.")
        for e in items:
            self.out(f"  {e.expense_id:<6} {e.date}  {e.category:<28} {format_pkr(e.amount):>14}  {e.description}")

    def view_category(self):
        grouped = self.active_budget.expenses_by_category()
        if not grouped:
            self.out("No expenses recorded yet.")
        for category, items in grouped.items():
            self.out(f"  {category}: {format_pkr(sum(e.amount for e in items))} ({len(items)} record(s))")
            for e in items:
                self.out(f"      {e.expense_id} {e.date} {format_pkr(e.amount)} {e.description}")

    def budget_summary(self):
        s = self.active_budget.summary()
        self.out(f"{s['budget_type']} - {s['month']}  | Available: {format_pkr(s['total_amount'])}")
        self.out(f"  {'Category':<28}{'Planned':>14}{'Actual':>14}{'Difference':>14}")
        for c, p, a, d in s["rows"]:
            self.out(f"  {c:<28}{format_pkr(p):>14}{format_pkr(a):>14}{format_pkr(d):>14}")
        self.out(f"  Planned {format_pkr(s['total_planned'])} | Actual {format_pkr(s['total_actual'])} | "
                 f"Remaining {format_pkr(s['remaining_balance'])}")
        self.out(f"  Savings {format_pkr(s['savings'])} ({s['savings_percentage']:.2f}%) | Unallocated {format_pkr(s['unallocated'])}")
        if s["overspent"]:
            self.out("  Overspent: " + ", ".join(f"{c} (+{format_pkr(a - p)})" for c, p, a, _ in s["overspent"]))
        if s["overall_overspent"]:
            self.out("  WARNING: overall spending exceeds the monthly budget.")
        if s["over_allocated"]:
            self.out("  WARNING: planned amounts exceed the monthly budget.")

    def confirm_budget(self):
        self.budget_summary()
        if self.yes_no("Confirm this budget?"):
            self.budgets.confirm_budget(self.active_budget)
            self.out("Budget confirmed.")
        else:
            self.out("Not confirmed.")

    def budget_pdf(self):
        path, _ = self.reports.generate_budget_report(self.active_budget)
        self.out(f"PDF created: {path}")

    # ---------- reports / developer ----------
    def show_previous(self):
        reports = self.dm.load_reports()
        self.out("Generated reports:" if reports else "No reports generated yet.")
        for r in reports:
            self.out(f"  {r.get('report_id')} | {r.get('title')} | {r.get('created')} | reports/{r.get('file')}")
        self.out(f"Saved trips: {len(self.dm.load_trips())} | Saved budgets: {len(self.budgets.list_budgets())}")

    def show_developer(self):
        d = self.developer
        self.out(f"Developer: {d['developer_name']}\nGitHub: {d['github_username']}\nEmail: {d['email']}")


if __name__ == "__main__":
    SmartLifePlanner().run()
    sys.exit(0)
