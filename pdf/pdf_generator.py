"""PDF creation with reportlab. Every page carries the developer footer and a page number."""
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from utils.calculations import format_pkr

# Plain (unencoded) page streams keep PDFs small here and let tests read text directly.
rl_config.useA85 = 0

NAVY = colors.HexColor("#1F3A5F")
LIGHT = colors.HexColor("#EEF2F7")
RED = colors.HexColor("#B3261E")
GREEN = colors.HexColor("#1B6E3C")


class PDFGenerationError(Exception):
    """Raised when a PDF cannot (or must not) be generated."""


class PDFReportGenerator:
    def __init__(self, developer):
        developer = developer if isinstance(developer, dict) else {}
        self.developer = {k: str(developer.get(k) or "Not provided")
                          for k in ("developer_name", "github_username", "email")}
        base = getSampleStyleSheet()
        self.styles = {
            "brand": ParagraphStyle("brand", parent=base["Title"], textColor=NAVY, fontSize=22, spaceAfter=2),
            "title": ParagraphStyle("title", parent=base["Heading2"], textColor=colors.HexColor("#444444"), spaceAfter=8),
            "h": ParagraphStyle("h", parent=base["Heading3"], textColor=NAVY, spaceBefore=10, spaceAfter=4),
            "body": ParagraphStyle("body", parent=base["Normal"], fontSize=9.5, leading=13),
            "small": ParagraphStyle("small", parent=base["Normal"], fontSize=8, leading=10, textColor=colors.grey),
        }

    # ---- shared building blocks ----
    def _footer(self, canvas, doc):
        canvas.saveState()
        width, _ = A4
        canvas.setStrokeColor(NAVY)
        canvas.line(18 * mm, 20 * mm, width - 18 * mm, 20 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#333333"))
        canvas.drawString(18 * mm, 15 * mm, f"Developer: {self.developer['developer_name']} | GitHub: {self.developer['github_username']}")
        canvas.drawString(18 * mm, 11 * mm, f"Email: {self.developer['email']}")
        canvas.drawRightString(width - 18 * mm, 15 * mm, f"Page {doc.page}")
        canvas.restoreState()

    def _table(self, rows, widths, header=True, align_right_from=1, highlight_last=False):
        table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
        style = [("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C5CCD6")),
                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4),
                 ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                 ("ALIGN", (align_right_from, 0), (-1, -1), "RIGHT")]
        if header:
            style += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                      ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
        for i in range(1 if header else 0, len(rows)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
        if highlight_last:
            style += [("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#DCE6F2"))]
        table.setStyle(TableStyle(style))
        return table

    def _p(self, text, style="body"):
        return Paragraph(escape(str(text)), self.styles[style])

    def _build(self, path, story, title):
        path = Path(path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            doc = SimpleDocTemplate(str(path), pagesize=A4, pageCompression=0, title=title,
                                    author=self.developer["developer_name"], leftMargin=18 * mm,
                                    rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=28 * mm)
            doc.build(story, onFirstPage=self._footer, onLaterPages=self._footer)
        except Exception as exc:  # reportlab raises many exception types
            raise PDFGenerationError(f"PDF generation failed: {exc}") from exc
        return path

    @staticmethod
    def _require(data, keys, kind):
        if not isinstance(data, dict):
            raise PDFGenerationError(f"Invalid {kind} report data.")
        missing = [k for k in keys if k not in data]
        if missing:
            raise PDFGenerationError(f"Invalid {kind} report data: missing {', '.join(missing)}.")
        if not data.get("confirmed"):
            raise PDFGenerationError("The plan must be reviewed and confirmed before a PDF can be generated.")

    def _header(self, title, report_id, date_text, extra=None):
        story = [self._p("Smart Life Planner", "brand"), self._p(title, "title")]
        rows = [["Report ID", report_id], ["Generated on", date_text]] + (extra or [])
        story += [self._table(rows, [45 * mm, 129 * mm], header=False, align_right_from=9), Spacer(1, 6)]
        return story

    # ---- trip report ----
    TRIP_KEYS = ("destination", "region", "departure_city", "travellers", "days", "nights", "transport",
                 "accommodation", "category", "transportation", "accommodation_cost", "food", "activities",
                 "miscellaneous", "emergency", "total", "cost_per_person", "budget", "difference",
                 "status", "is_over", "rooms")

    def generate_trip_pdf(self, summary, itinerary, report_id, date_text, path):
        self._require(summary, self.TRIP_KEYS, "trip")
        s = summary
        story = self._header("Pakistan Trip Plan", report_id, date_text)
        story.append(self._p("Trip Details", "h"))
        story.append(self._table([
            ["Destination", f"{s['destination']} ({s['region']})"], ["Departure city", s["departure_city"]],
            ["Travellers", str(s["travellers"])], ["Days / Nights", f"{s['days']} days / {s['nights']} nights"],
            ["Travel category", s["category"]], ["Transportation", s["transport"]],
            ["Accommodation", f"{s['accommodation']} ({s['rooms']} room{'s' if s['rooms'] != 1 else ''})"],
        ], [45 * mm, 129 * mm], header=False, align_right_from=9))
        story.append(self._p("Cost Breakdown", "h"))
        rows = [["Item", "Amount"], ["Transportation", format_pkr(s["transportation"])],
                ["Accommodation", format_pkr(s["accommodation_cost"])], ["Food", format_pkr(s["food"])],
                ["Activities", format_pkr(s["activities"])], ["Miscellaneous expenses", format_pkr(s["miscellaneous"])],
                [f"Emergency allowance ({s.get('emergency_percentage', '')}%)", format_pkr(s["emergency"])],
                ["Total estimated cost", format_pkr(s["total"])]]
        story.append(self._table(rows, [110 * mm, 64 * mm], highlight_last=True))
        story.append(Spacer(1, 6))
        label = "Shortage" if s["is_over"] else "Remaining balance"
        story.append(self._table([
            ["Cost per person", format_pkr(s["cost_per_person"])], ["Available budget", format_pkr(s["budget"])],
            [label, format_pkr(abs(s["difference"]))], ["Final feasibility status", s["status"]],
        ], [110 * mm, 64 * mm], header=False))
        story.append(self._p("Day-wise Itinerary", "h"))
        for day in itinerary:
            story.append(self._p(f"Day {day.day}: {day.title}", "body"))
            for item in day.items:
                story.append(self._p(f"   - {item}", "body"))
            story.append(Spacer(1, 4))
        story.append(Spacer(1, 6))
        story.append(self._p(s.get("disclaimer", "Costs are estimates, not guaranteed market prices."), "small"))
        return self._build(path, story, "Pakistan Trip Plan")

    # ---- monthly budget report ----
    BUDGET_KEYS = ("month", "budget_type", "total_amount", "rows", "total_planned", "total_actual",
                   "remaining_balance", "savings", "savings_percentage", "overspent", "unallocated")

    def generate_budget_pdf(self, summary, report_id, date_text, path):
        self._require(summary, self.BUDGET_KEYS, "budget")
        s = summary
        story = self._header("Monthly Financial Report", report_id, date_text,
                             [["Budget month", s["month"]], ["Budget type", s["budget_type"]],
                              ["Total available amount", format_pkr(s["total_amount"])]])
        story.append(self._p("Category-wise Summary", "h"))
        rows = [["Category", "Planned", "Actual", "Difference"]]
        rows += [[c, format_pkr(p), format_pkr(a), format_pkr(d)] for c, p, a, d in s["rows"]]
        rows.append(["TOTAL", format_pkr(s["total_planned"]), format_pkr(s["total_actual"]),
                     format_pkr(s["total_planned"] - s["total_actual"])])
        story.append(self._table(rows, [64 * mm, 36 * mm, 36 * mm, 38 * mm], highlight_last=True))
        story.append(self._p("Financial Summary", "h"))
        story.append(self._table([
            ["Total planned expenses", format_pkr(s["total_planned"])],
            ["Total actual expenses", format_pkr(s["total_actual"])],
            ["Remaining balance", format_pkr(s["remaining_balance"])],
            ["Savings", format_pkr(s["savings"])],
            ["Savings percentage", f"{s['savings_percentage']:.2f}%"],
            ["Unallocated amount", format_pkr(s["unallocated"])],
        ], [110 * mm, 64 * mm], header=False))
        story.append(self._p("Overspending", "h"))
        if s["overspent"]:
            rows = [["Category", "Planned", "Actual", "Over by"]]
            rows += [[c, format_pkr(p), format_pkr(a), format_pkr(a - p)] for c, p, a, _ in s["overspent"]]
            story.append(self._table(rows, [64 * mm, 36 * mm, 36 * mm, 38 * mm]))
        else:
            story.append(self._p("No category is overspent."))
        if s.get("overall_overspent"):
            story.append(self._p("WARNING: total actual spending exceeds the monthly budget."))
        return self._build(path, story, "Monthly Financial Report")
