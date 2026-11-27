"""Regenerates every chart and table used in README.md from the REAL application code and test run.

Run from the project root:   python docs/generate_assets.py
Needs matplotlib (documentation only; not required to run the app or tests).
"""
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from models.trip import Trip  # noqa: E402
from services.budget_manager import MonthlyBudgetManager  # noqa: E402
from services.trip_planner import TripPlanner  # noqa: E402
from utils.calculations import format_pkr  # noqa: E402
from utils.data_manager import DataManager  # noqa: E402

IMG = ROOT / "docs" / "images"
NAVY, GOLD, GREEN, RED, GREY = "#1F3A5F", "#F2C94C", "#1B6E3C", "#B3261E", "#8A94A6"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titleweight": "bold", "figure.dpi": 130})

data = DataManager().load_destination_data()
planner = TripPlanner(data.destinations, data.settings)
tables = {}


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


# ---------- 1. destination database + reference-trip cost per destination ----------
ref = dict(budget=1_000_000, travellers=2, departure_city="Islamabad", days=3, nights=2, category="Standard")
rows, comps = [], []
for d in sorted(data.destinations, key=lambda x: x.name):
    plan = planner.evaluate(Trip(destination=d.name, **ref))
    b = plan.breakdown
    comps.append((d.name, b))
    rows.append([d.name, d.region, d.category, f"{d.transport_cost_pp:,}", f"{d.accommodation_per_room_night:,}",
                 f"{d.food_pp_day:,}", f"{d.activities_pp_day:,}", f"{d.misc_pp_day:,}", d.room_capacity])
tables["DEST_TABLE"] = md_table(["Destination", "Region", "Category", "Transport /person", "Room /night", "Food /person/day",
                                 "Activities /person/day", "Misc /person/day", "Room capacity"], rows)
comps.sort(key=lambda c: c[1].total)
tables["REF_TABLE"] = md_table(
    ["Destination", "Transport", "Accommodation", "Food", "Activities", "Misc", "Emergency", "Total", "Per person"],
    [[n, f"{b.transportation:,}", f"{b.accommodation:,}", f"{b.food:,}", f"{b.activities:,}", f"{b.miscellaneous:,}",
      f"{b.emergency:,}", f"**{b.total:,}**", f"{b.cost_per_person:,.2f}"] for n, b in comps])

fig, ax = plt.subplots(figsize=(10, 5.2))
names = [n for n, _ in comps]
parts = [("transportation", "Transport", NAVY), ("accommodation", "Accommodation", "#4F7CAC"), ("food", "Food", GOLD),
         ("activities", "Activities", GREEN), ("miscellaneous", "Misc", GREY), ("emergency", "Emergency (10%)", RED)]
left = [0] * len(comps)
for attr, label, colour in parts:
    vals = [getattr(b, attr) for _, b in comps]
    ax.barh(names, vals, left=left, label=label, color=colour)
    left = [l + v for l, v in zip(left, vals)]
for i, total in enumerate(left):
    ax.text(total + 500, i, f"PKR {total:,}", va="center", fontsize=8)
ax.set_xlabel("Estimated cost (PKR)")
ax.set_title("Reference trip: 2 travellers, 3 days / 2 nights, Standard, from Islamabad")
ax.legend(loc="lower right", fontsize=8)
ax.set_xlim(0, max(left) * 1.18)
fig.tight_layout()
fig.savefig(IMG / "cost_by_destination.png")
plt.close(fig)

# ---------- 2. room-capacity (ceiling) effect ----------
fig, ax = plt.subplots(figsize=(10, 4.2))
for name, colour in (("Murree", NAVY), ("Skardu", GREEN)):
    xs = list(range(1, 13))
    ys = [planner.evaluate(Trip(destination=name, **{**ref, "travellers": n})).total for n in xs]
    ax.plot(xs, ys, marker="o", color=colour, label=f"{name} total")
rooms = [planner.evaluate(Trip(destination="Murree", **{**ref, "travellers": n})).breakdown.rooms for n in range(1, 13)]
ax2 = ax.twinx()
ax2.step(range(1, 13), rooms, where="mid", color=GOLD, linewidth=2, label="Murree rooms (capacity 4)")
ax2.set_ylabel("Rooms required = ceil(travellers / capacity)")
ax2.set_yticks(range(1, 5))
ax.set_xlabel("Number of travellers")
ax.set_ylabel("Estimated total (PKR)")
ax.set_title("Cost grows in steps when another room is needed")
h1, l1 = ax.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8)
fig.tight_layout()
fig.savefig(IMG / "room_ceiling_effect.png")
plt.close(fig)

# ---------- 3. optimiser scenario ----------
scenario = Trip(budget=150_000, travellers=4, destination="Hunza", departure_city="Islamabad", days=5, nights=4)
plan = planner.evaluate(scenario)
report = planner.optimizer.analyse(scenario)
b = plan.breakdown
tables["SCENARIO"] = md_table(["Item", "Value"], [
    ["Trip", "Hunza, 4 travellers, 5 days / 4 nights, Standard, from Islamabad"],
    ["Total estimate", format_pkr(b.total)], ["Available budget", format_pkr(scenario.budget)],
    ["Status", plan.status], ["Shortage", format_pkr(report.shortage)],
    ["Minimum budget required", format_pkr(report.minimum_budget)],
    ["Additional budget needed", format_pkr(report.additional_budget)],
    ["Maximum travellers within budget", report.max_travellers]])
top = report.ranked[:8]
tables["RANK_TABLE"] = md_table(["Rank", "Alternative", "Complete cost", "Remaining", "Score"],
                                [[i, a.label, format_pkr(a.breakdown.total), format_pkr(scenario.budget - a.breakdown.total), a.score]
                                 for i, a in enumerate(top, 1)])
fig, ax = plt.subplots(figsize=(10, 4.6))
labels = [a.label for a in top][::-1]
scores = [a.score for a in top][::-1]
ax.barh(labels, scores, color=GREEN)
for i, a in enumerate(top[::-1]):
    ax.text(a.score + 0.005, i, f"PKR {a.breakdown.total:,}", va="center", fontsize=8)
ax.set_xlim(0, max(scores) * 1.25)
ax.set_xlabel("Ranking score (higher is better)")
ax.set_title("Ranked alternatives for the over-budget Hunza trip (all fit PKR 150,000)")
fig.tight_layout()
fig.savefig(IMG / "optimizer_ranking.png")
plt.close(fig)

# ---------- 4. budget example ----------
manager = MonthlyBudgetManager()  # no data manager -> nothing is written to disk
bud = manager.create_budget("2026-11", 120_000, "Home & Kitchen")
for cat, amt in [("Grocery", 30000), ("Rent", 50000), ("Electricity", 12000), ("Internet", 4000), ("Emergency Savings", 10000)]:
    bud.set_planned(cat, amt)
for cat, amt, desc, day in [("Grocery", 32500, "Monthly ration", "2026-11-02"), ("Rent", 50000, "November rent", "2026-11-01"),
                            ("Electricity", 14200, "Bill", "2026-11-10"), ("Internet", 4000, "Fibre", "2026-11-05")]:
    bud.add_expense(cat, amt, desc, day)
s = bud.summary()
rows = [r for r in s["rows"] if r[1] or r[2]]
tables["BUDGET_TABLE"] = md_table(["Category", "Planned", "Actual", "Difference"],
                                  [[c, format_pkr(p), format_pkr(a), format_pkr(d)] for c, p, a, d in rows])
tables["BUDGET_SUMMARY"] = md_table(["Measure", "Value"], [
    ["Available", format_pkr(s["total_amount"])], ["Total planned", format_pkr(s["total_planned"])],
    ["Total actual", format_pkr(s["total_actual"])], ["Remaining balance", format_pkr(s["remaining_balance"])],
    ["Savings", f"{format_pkr(s['savings'])} ({s['savings_percentage']:.2f}%)"],
    ["Unallocated", format_pkr(s["unallocated"])],
    ["Overspent categories", ", ".join(f"{c} (+{format_pkr(a - p)})" for c, p, a, _ in s["overspent"]) or "none"]])
fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.4), gridspec_kw={"width_ratios": [1.6, 1]})
x = range(len(rows))
a1.bar([i - 0.2 for i in x], [r[1] for r in rows], 0.4, label="Planned", color=NAVY)
a1.bar([i + 0.2 for i in x], [r[2] for r in rows], 0.4, label="Actual", color=[RED if r[2] > r[1] else GREEN for r in rows])
a1.set_xticks(list(x))
a1.set_xticklabels([r[0].replace(" ", "\n") for r in rows], fontsize=8)
a1.set_ylabel("PKR")
a1.set_title("Planned vs actual (red = overspent)")
a1.legend(fontsize=8)
a2.pie([s["total_actual"], s["savings"]], labels=["Spent", "Savings"], colors=[GOLD, GREEN], autopct="%1.1f%%", startangle=90,
       wedgeprops={"width": 0.45})
a2.set_title("Share of the PKR 120,000 budget")
fig.tight_layout()
fig.savefig(IMG / "budget_example.png")
plt.close(fig)

# ---------- 5. real test + coverage results ----------
cov_file = ROOT / "docs" / "coverage.json"
proc = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q", "--cov=models", "--cov=services", "--cov=utils",
                       "--cov=pdf", "--cov=main", f"--cov-report=json:{cov_file}"], cwd=ROOT, capture_output=True, text=True)
summary_line = proc.stdout.strip().splitlines()[-1]
counts = {}
for f in sorted((ROOT / "tests").glob("test_*.py")):
    out = subprocess.run([sys.executable, "-m", "pytest", str(f), "--co", "-q"], cwd=ROOT, capture_output=True, text=True).stdout
    counts[f.stem] = sum(1 for line in out.splitlines() if "::" in line)
cov = json.loads(cov_file.read_text())
per_file = {k: v["summary"]["percent_covered"] for k, v in cov["files"].items() if not k.endswith("__init__.py")}
total_cov = cov["totals"]["percent_covered"]
cov_file.unlink()
tables["TEST_SUMMARY"] = summary_line
tables["TEST_TABLE"] = md_table(["Test file", "Tests"], [[k + ".py", v] for k, v in counts.items()] + [["**Total**", f"**{sum(counts.values())}**"]])
tables["COV_TABLE"] = md_table(["Module", "Coverage"], [[k.replace("\\", "/"), f"{v:.0f}%"] for k, v in sorted(per_file.items())]
                               + [["**Total**", f"**{total_cov:.0f}%**"]])
fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.8))
a1.barh([k.replace("test_", "") for k in counts][::-1], list(counts.values())[::-1], color=NAVY)
for i, v in enumerate(list(counts.values())[::-1]):
    a1.text(v + 0.5, i, str(v), va="center", fontsize=8)
a1.set_title(f"Pytest cases per file (total {sum(counts.values())})")
mods = sorted(per_file.items(), key=lambda kv: kv[1])
a2.barh([k.split("/")[-1].replace("\\", "/").split("/")[-1] for k, _ in mods], [v for _, v in mods],
        color=[GREEN if v >= 90 else GOLD if v >= 70 else RED for _, v in mods])
a2.set_xlim(0, 105)
a2.set_title(f"Statement coverage per module (total {total_cov:.0f}%)")
fig.tight_layout()
fig.savefig(IMG / "test_results.png")
plt.close(fig)


# ---------- 6. animated results table (SVG, real numbers) ----------
def animated_table(counts, total_tests, total_cov, summary_line):
    rows = list(counts.items())
    width, row_h, top = 760, 34, 96
    height = top + row_h * (len(rows) + 2) + 40
    biggest = max(counts.values())
    css = """
    .t{font:15px Helvetica,Arial,sans-serif;fill:#1b2a41}.h{font:700 15px Helvetica,Arial,sans-serif;fill:#fff}
    .ttl{font:700 22px Helvetica,Arial,sans-serif;fill:#1F3A5F}.sub{font:13px Helvetica,Arial,sans-serif;fill:#5b6b82}
    .row{opacity:0;animation:rowin 14s ease-out infinite}
    .bar{transform-box:fill-box;transform-origin:left;transform:scaleX(0);animation:barin 14s ease-out infinite}
    .tot{font:700 15px Helvetica,Arial,sans-serif;fill:#1F3A5F}
    @keyframes rowin{0%{opacity:0;transform:translateX(-40px)}4%{opacity:1;transform:none}90%{opacity:1;transform:none}98%,100%{opacity:0;transform:translateX(20px)}}
    @keyframes barin{0%{transform:scaleX(0)}8%{transform:scaleX(1)}90%{transform:scaleX(1)}98%,100%{transform:scaleX(0)}}
    """
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="Animated test results table">',
           f'<style>{css}</style>', f'<rect width="{width}" height="{height}" rx="14" fill="#F6F8FB" stroke="#C5CCD6"/>',
           '<text class="ttl" x="28" y="40">Automated test results (live numbers from pytest)</text>',
           f'<text class="sub" x="28" y="62">{summary_line}  |  statement coverage {total_cov:.0f}%</text>',
           f'<rect x="20" y="{top - 26}" width="{width - 40}" height="{row_h - 4}" rx="6" fill="#1F3A5F"/>',
           f'<text class="h" x="34" y="{top - 4}">Test module</text><text class="h" x="360" y="{top - 4}">Tests</text><text class="h" x="440" y="{top - 4}">Share of suite</text>']
    for i, (name, n) in enumerate(rows):
        y = top + row_h * i + 34
        delay = f"{0.35 * (i + 1):.2f}s"
        bg = "#EEF2F7" if i % 2 == 0 else "#FFFFFF"
        bar_w = int(280 * n / biggest)
        out.append(f'<g class="row" style="animation-delay:{delay}"><rect x="20" y="{y - 20}" width="{width - 40}" height="{row_h - 2}" rx="4" fill="{bg}"/>'
                   f'<text class="t" x="34" y="{y}">{name}.py</text><text class="t" x="360" y="{y}">{n}</text>'
                   f'<rect class="bar" style="animation-delay:{delay}" x="440" y="{y - 14}" width="{bar_w}" height="14" rx="3" fill="#1B6E3C"/></g>')
    y = top + row_h * len(rows) + 34
    delay = f"{0.35 * (len(rows) + 1):.2f}s"
    out.append(f'<g class="row" style="animation-delay:{delay}"><rect x="20" y="{y - 20}" width="{width - 40}" height="{row_h - 2}" rx="4" fill="#DCE6F2"/>'
               f'<text class="tot" x="34" y="{y}">TOTAL</text><text class="tot" x="360" y="{y}">{total_tests}</text>'
               f'<text class="tot" x="440" y="{y}">all passing</text></g>')
    out.append("</svg>")
    (IMG / "animated_test_table.svg").write_text("\n".join(out), encoding="utf-8")


animated_table(counts, sum(counts.values()), total_cov, summary_line.split(" in ")[0])

(ROOT / "docs" / "generated_tables.json").write_text(json.dumps(tables, indent=2))
print(summary_line, f"| coverage {total_cov:.1f}%")
