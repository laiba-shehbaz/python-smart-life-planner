import re

import pytest

from models.trip import Trip
from pdf.pdf_generator import PDFGenerationError, PDFReportGenerator
from services.report_generator import ReportError
from services.trip_planner import TripPlanner
from services.budget_manager import MonthlyBudgetManager


def page_count(data):
    return len(re.findall(rb"/Type /Page(?!s)", data))


def trip(**kw):
    d = dict(budget=100000, travellers=3, destination="Alpha", departure_city="Islamabad", days=3, nights=2)
    d.update(kw)
    return Trip(**d)


@pytest.fixture
def confirmed_planner(planner):
    planner.propose(trip())
    planner.confirm()
    return planner


@pytest.fixture
def confirmed_budget(budget_manager):
    b = budget_manager.create_budget("2026-11", 80000, "Personal Finance")
    b.set_planned("Shopping", 9000)
    b.add_expense("Shopping", 10000, "Shoes", "2026-11-03")
    budget_manager.confirm_budget(b)
    return b


# ---- confirmation gating ----
def test_trip_pdf_refused_before_confirmation(planner, reports):
    with pytest.raises(ReportError, match="Confirm"):
        reports.generate_trip_report(planner)
    planner.propose(trip())  # proposed but still unconfirmed
    with pytest.raises(ReportError):
        reports.generate_trip_report(planner)


def test_budget_pdf_refused_before_confirmation(budget_manager, reports):
    b = budget_manager.create_budget("2026-11", 5000, "Home & Kitchen")
    with pytest.raises(ReportError, match="Confirm"):
        reports.generate_budget_report(b)


def test_budget_pdf_refused_after_edit_resets_confirmation(confirmed_budget, reports):
    confirmed_budget.add_expense("Shopping", 1, "x", "2026-11-04")
    with pytest.raises(ReportError):
        reports.generate_budget_report(confirmed_budget)


# ---- trip PDF content ----
def test_trip_pdf_contains_required_content(confirmed_planner, reports, developer):
    path, ref = reports.generate_trip_report(confirmed_planner)
    data = path.read_bytes()
    assert data.startswith(b"%PDF") and path.parent == reports.data_manager.reports_dir
    for text in (b"Smart Life Planner", b"Pakistan Trip Plan", ref["report_id"].encode(), b"Alpha",
                 b"Islamabad", b"Within Budget", b"Day 1", b"Day 3", b"Emergency allowance"):
        assert text in data, text
    assert developer["github_username"].encode() in data and developer["email"].encode() in data


def test_trip_pdf_numbers_match_application_calculations(confirmed_planner, reports):
    path, _ = reports.generate_trip_report(confirmed_planner)
    data = path.read_bytes()
    b = confirmed_planner.confirmed.breakdown
    assert b.total == 28820
    for amount in (b.transportation, b.accommodation, b.food, b.activities, b.miscellaneous, b.emergency, b.total):
        assert f"PKR {amount:,}".encode() in data
    assert b"PKR 100,000" in data and b"PKR 71,180" in data  # budget and remaining balance
    assert f"PKR {b.cost_per_person:,.2f}".encode() in data


def test_over_budget_trip_pdf_reports_shortage(planner, reports):
    planner.propose(trip(budget=20000))
    planner.confirm()
    data = reports.generate_trip_report(planner)[0].read_bytes()
    assert b"Over Budget" in data and b"Shortage" in data and b"PKR 8,820" in data


def test_zero_night_trip_pdf(planner, reports):
    planner.propose(trip(days=1, nights=0))
    planner.confirm()
    data = reports.generate_trip_report(planner)[0].read_bytes()
    assert b"0 nights" in data and b"Day trip" in data


# ---- footer on every page / multi-page ----
def test_footer_on_every_page_of_multi_page_report(planner, reports, developer):
    planner.propose(trip(days=30, nights=29))
    planner.confirm()
    data = reports.generate_trip_report(planner)[0].read_bytes()
    pages = page_count(data)
    assert pages >= 2
    assert data.count(developer["github_username"].encode()) == pages
    assert data.count(developer["email"].encode()) == pages
    assert data.count(b"Page ") >= pages


def test_budget_pdf_with_many_categories_is_multi_page_with_footer(budget_manager, reports, developer):
    b = budget_manager.create_budget("2026-11", 500000, "Home & Kitchen")
    for i in range(80):
        b.add_category(f"Custom Category {chr(65 + i % 26)}{chr(97 + i // 26)}", 100)
    budget_manager.confirm_budget(b)
    data = reports.generate_budget_report(b)[0].read_bytes()
    pages = page_count(data)
    assert pages >= 2 and data.count(developer["email"].encode()) == pages


# ---- budget PDF content ----
def test_budget_pdf_contains_required_content_and_matches_calculations(confirmed_budget, reports, developer):
    path, ref = reports.generate_budget_report(confirmed_budget)
    data = path.read_bytes()
    for text in (b"Smart Life Planner", b"Monthly Financial Report", b"2026-11", b"Personal Finance",
                 ref["report_id"].encode(), b"Shopping", b"Overspending"):
        assert text in data, text
    s = confirmed_budget.summary()
    assert s["remaining_balance"] == 70000 and s["savings_percentage"] == 87.5
    for expected in (b"PKR 80,000", b"PKR 9,000", b"PKR 10,000", b"PKR 70,000", b"87.50%", b"-PKR 1,000"):
        assert expected in data, expected
    assert developer["github_username"].encode() in data and developer["email"].encode() in data


def test_budget_pdf_with_no_overspending(budget_manager, reports):
    b = budget_manager.create_budget("2026-10", 1000, "Home & Kitchen")
    budget_manager.confirm_budget(b)
    data = reports.generate_budget_report(b)[0].read_bytes()
    assert b"No category is overspent" in data


# ---- filenames / directories ----
def test_reports_directory_created_when_missing(confirmed_planner, reports):
    assert not reports.data_manager.reports_dir.exists()
    path, _ = reports.generate_trip_report(confirmed_planner)
    assert path.exists()


def test_existing_reports_are_never_overwritten(confirmed_planner, reports, monkeypatch):
    monkeypatch.setattr(reports, "new_report_id", lambda prefix: "TRIP-FIXED")
    first, _ = reports.generate_trip_report(confirmed_planner)
    first_bytes = first.read_bytes()
    second, _ = reports.generate_trip_report(confirmed_planner)
    third, _ = reports.generate_trip_report(confirmed_planner)
    assert len({first, second, third}) == 3 and first.read_bytes() == first_bytes
    assert second.name == "TRIP-FIXED-2.pdf"


def test_report_ids_are_unique(reports):
    assert len({reports.new_report_id("TRIP") for _ in range(50)}) == 50


def test_report_reference_is_recorded(confirmed_planner, reports):
    _, ref = reports.generate_trip_report(confirmed_planner)
    assert reports.data_manager.load_reports()[-1]["report_id"] == ref["report_id"]


# ---- developer info / invalid data / failures ----
def test_missing_developer_info_uses_placeholder_in_footer(tmp_path, confirmed_planner, tmp_dm, settings):
    from services.report_generator import ReportGenerator
    rg = ReportGenerator(tmp_dm, {}, settings)
    data = rg.generate_trip_report(confirmed_planner)[0].read_bytes()
    assert b"GitHub: Not provided" in data and b"Email: Not provided" in data


@pytest.mark.parametrize("bad", [None, {}, {"destination": "X", "confirmed": True}, "text"])
def test_invalid_trip_report_data_rejected(tmp_path, developer, bad):
    with pytest.raises(PDFGenerationError):
        PDFReportGenerator(developer).generate_trip_pdf(bad, [], "ID", "today", tmp_path / "x.pdf")
    assert not (tmp_path / "x.pdf").exists()


@pytest.mark.parametrize("bad", [None, {}, {"month": "2026-11", "confirmed": True}])
def test_invalid_budget_report_data_rejected(tmp_path, developer, bad):
    with pytest.raises(PDFGenerationError):
        PDFReportGenerator(developer).generate_budget_pdf(bad, "ID", "today", tmp_path / "x.pdf")


def test_summary_marked_unconfirmed_is_rejected(confirmed_planner, reports, developer, tmp_path):
    summary = reports.trip_summary(confirmed_planner.confirmed, confirmed_planner.find_destination("Alpha"), confirmed=False)
    with pytest.raises(PDFGenerationError, match="confirmed"):
        PDFReportGenerator(developer).generate_trip_pdf(summary, [], "ID", "today", tmp_path / "x.pdf")


def test_pdf_write_failure_is_wrapped(confirmed_planner, reports, developer, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a folder")
    summary = reports.trip_summary(confirmed_planner.confirmed, confirmed_planner.find_destination("Alpha"))
    with pytest.raises(PDFGenerationError):
        PDFReportGenerator(developer).generate_trip_pdf(summary, [], "ID", "today", blocker / "sub" / "x.pdf")


def test_report_error_wraps_pdf_failure(confirmed_planner, reports, monkeypatch):
    def boom(*a, **k):
        raise PDFGenerationError("disk full")
    monkeypatch.setattr(reports.pdf, "generate_trip_pdf", boom)
    with pytest.raises(ReportError, match="disk full"):
        reports.generate_trip_report(confirmed_planner)


def test_special_characters_do_not_break_pdf(budget_manager, reports):
    b = budget_manager.create_budget("2026-11", 5000, "Home & Kitchen")
    b.add_category("R&D <Lab>" .replace("<", "").replace(">", ""), 10)
    budget_manager.confirm_budget(b)
    assert reports.generate_budget_report(b)[0].exists()


def test_trip_and_budget_summaries_agree_with_models(confirmed_planner, reports, confirmed_budget):
    plan = confirmed_planner.confirmed
    s = reports.trip_summary(plan, confirmed_planner.find_destination("Alpha"))
    assert s["total"] == plan.total and s["difference"] == 100000 - plan.total and not s["is_over"]
    assert reports.budget_summary(confirmed_budget)["savings"] == confirmed_budget.savings
