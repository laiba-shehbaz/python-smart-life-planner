"""Builds the RUNNING (looping) animations used in README.md from the real application data:
animated GIF charts (bars grow, lines draw, donut fills) and animated SVG tables.

Run from the project root:   python docs/make_animations.py      (needs matplotlib, Pillow, pytest-cov)
"""
import io
import json
import math
from xml.sax.saxutils import escape as xesc
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from models.trip import Trip  # noqa: E402
from services.budget_manager import MonthlyBudgetManager  # noqa: E402
from services.trip_planner import TripPlanner  # noqa: E402
from utils.calculations import format_pkr  # noqa: E402
from utils.data_manager import DataManager  # noqa: E402

IMG = ROOT / "docs" / "images"
NAVY, GOLD, GREEN, RED, GREY, BLUE = "#1F3A5F", "#F2C94C", "#1B6E3C", "#B3261E", "#8A94A6", "#4F7CAC"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titleweight": "bold"})
GROW, HOLD = 34, 16  # frames


def ease(t):
    return 1 - (1 - t) ** 3


def progress():
    """t values for one loop: grow with easing, then hold."""
    return [ease((i + 1) / GROW) for i in range(GROW)] + [1.0] * HOLD


def to_gif(draw, path, size=(9.6, 4.8), dpi=90, frame_ms=45):
    frames = []
    for t in progress():
        fig = plt.figure(figsize=size, dpi=dpi)
        draw(fig, t)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor="white")
        plt.close(fig)
        frames.append(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"))
    pal = [f.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    times = [frame_ms] * len(pal)
    times[-1] = 1400
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=times, loop=0, optimize=True)
    print(path.name, f"{path.stat().st_size // 1024} KB", len(pal), "frames")


# ------------------------------------------------------------------ real data
data = DataManager().load_destination_data()
planner = TripPlanner(data.destinations, data.settings)
ref = dict(budget=1_000_000, travellers=2, departure_city="Islamabad", days=3, nights=2, category="Standard")
comps = sorted(((d.name, planner.evaluate(Trip(destination=d.name, **ref)).breakdown) for d in data.destinations),
               key=lambda c: c[1].total)
scenario = Trip(budget=150_000, travellers=4, destination="Hunza", departure_city="Islamabad", days=5, nights=4)
ranked = planner.optimizer.analyse(scenario).ranked[:8]
mgr = MonthlyBudgetManager()
bud = mgr.create_budget("2026-11", 120_000, "Home & Kitchen")
for c, a in [("Grocery", 30000), ("Rent", 50000), ("Electricity", 12000), ("Internet", 4000), ("Emergency Savings", 10000)]:
    bud.set_planned(c, a)
for c, a, d, dt in [("Grocery", 32500, "Monthly ration", "2026-11-02"), ("Rent", 50000, "November rent", "2026-11-01"),
                    ("Electricity", 14200, "Bill", "2026-11-10"), ("Internet", 4000, "Fibre", "2026-11-05")]:
    bud.add_expense(c, a, d, dt)
summ = bud.summary()
brows = [r for r in summ["rows"] if r[1] or r[2]]


# ------------------------------------------------------------------ GIF charts
def cost_chart(fig, t):
    ax = fig.add_axes([0.12, 0.13, 0.84, 0.76])
    parts = [("transportation", "Transport", NAVY), ("accommodation", "Accommodation", BLUE), ("food", "Food", GOLD),
             ("activities", "Activities", GREEN), ("miscellaneous", "Misc", GREY), ("emergency", "Emergency", RED)]
    left = [0.0] * len(comps)
    for attr, label, col in parts:
        vals = [getattr(b, attr) * t for _, b in comps]
        ax.barh([n for n, _ in comps], vals, left=left, label=label, color=col)
        left = [l + v for l, v in zip(left, vals)]
    for i, tot in enumerate(left):
        ax.text(tot + 800, i, f"PKR {int(tot):,}", va="center", fontsize=7.5)
    ax.set_xlim(0, comps[-1][1].total * 1.2)
    ax.set_xlabel("Estimated cost (PKR)")
    ax.set_title("2 travellers, 3 days / 2 nights, Standard, from Islamabad", fontsize=10)
    ax.legend(loc="lower right", fontsize=7, ncol=2)


def room_chart(fig, t):
    import numpy as np
    ax = fig.add_axes([0.09, 0.14, 0.80, 0.74])
    xs = list(range(1, 13))
    pos = 1 + t * (len(xs) - 1)  # fractional x reached by the animation
    fine = np.linspace(1, pos, max(2, int(40 * t) + 2))
    for name, col in (("Murree", NAVY), ("Skardu", GREEN)):
        ys = [planner.evaluate(Trip(destination=name, **{**ref, "travellers": x})).total for x in xs]
        ax.plot(fine, np.interp(fine, xs, ys), color=col, label=f"{name} total")
        k = [x for x in xs if x <= pos]
        ax.plot(k, ys[:len(k)], "o", color=col)
    rooms = [planner.evaluate(Trip(destination="Murree", **{**ref, "travellers": x})).breakdown.rooms for x in xs]
    ax2 = ax.twinx()
    k = [x for x in xs if x <= pos]
    ax2.step(k, rooms[:len(k)], where="mid", color=GOLD, linewidth=2.2, label="Murree rooms (capacity 4)")
    ax.set_xlim(0.5, 12.5)
    ax.set_ylim(0, 340000)
    ax2.set_ylim(0, 4.5)
    ax2.set_yticks(range(1, 5))
    ax2.set_ylabel("Rooms = ceil(travellers / capacity)")
    ax.set_xlabel("Travellers")
    ax.set_ylabel("Estimated total (PKR)")
    ax.set_title("Cost grows in steps when another room is needed", fontsize=10)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=7)


def ranking_chart(fig, t):
    ax = fig.add_axes([0.40, 0.13, 0.56, 0.74])
    labels = [a.label for a in ranked][::-1]
    scores = [a.score for a in ranked][::-1]
    ax.barh(labels, [s * t for s in scores], color=GREEN)
    for i, a in enumerate(ranked[::-1]):
        ax.text(a.score * t + 0.01, i, f"{format_pkr(a.breakdown.total)}", va="center", fontsize=7.5)
    ax.set_xlim(0, max(scores) * 1.35)
    ax.set_xlabel("Ranking score")
    ax.set_title("Alternatives for the over-budget Hunza trip (all fit PKR 150,000)", fontsize=10)


def budget_chart(fig, t):
    a1 = fig.add_axes([0.07, 0.2, 0.60, 0.68])
    x = range(len(brows))
    a1.bar([i - 0.2 for i in x], [r[1] * t for r in brows], 0.4, label="Planned", color=NAVY)
    a1.bar([i + 0.2 for i in x], [r[2] * t for r in brows], 0.4, label="Actual",
           color=[RED if r[2] > r[1] else GREEN for r in brows])
    a1.set_xticks(list(x))
    a1.set_xticklabels([r[0].replace(" ", "\n") for r in brows], fontsize=7.5)
    a1.set_ylim(0, 58000)
    a1.set_title("Planned vs actual (red = overspent)", fontsize=10)
    a1.legend(fontsize=7)
    a2 = fig.add_axes([0.68, 0.1, 0.30, 0.78])
    a2.pie([summ["total_actual"] * t, summ["total_amount"] - summ["total_actual"] * t], colors=[GOLD, "#E3E8EF"],
           startangle=90, counterclock=False, wedgeprops={"width": 0.42})
    a2.text(0, 0, f"{summ['total_actual'] * t / summ['total_amount'] * 100:.0f}%\nspent", ha="center", va="center", fontsize=11, fontweight="bold")
    a2.set_title("Share of PKR 120,000", fontsize=10)


def test_chart(fig, t):
    counts = json.loads((ROOT / "docs" / "test_counts.json").read_text())
    ax = fig.add_axes([0.30, 0.12, 0.66, 0.76])
    names = [k.replace("test_", "") for k in counts][::-1]
    vals = list(counts.values())[::-1]
    ax.barh(names, [v * t for v in vals], color=NAVY)
    for i, v in enumerate(vals):
        ax.text(v * t + 0.8, i, str(int(round(v * t))), va="center", fontsize=8)
    ax.set_xlim(0, max(vals) * 1.15)
    ax.set_title(f"Pytest cases per file (total {sum(counts.values())})", fontsize=10)


# test counts (real, from pytest collection)
counts = {}
for f in sorted((ROOT / "tests").glob("test_*.py")):
    out = subprocess.run([sys.executable, "-m", "pytest", str(f), "--co", "-q"], cwd=ROOT, capture_output=True, text=True).stdout
    counts[f.stem] = sum(1 for line in out.splitlines() if "::" in line)
(ROOT / "docs" / "test_counts.json").write_text(json.dumps(counts))

to_gif(cost_chart, IMG / "cost_by_destination.gif")
to_gif(room_chart, IMG / "room_ceiling_effect.gif", size=(9.6, 4.2))
to_gif(ranking_chart, IMG / "optimizer_ranking.gif")
to_gif(budget_chart, IMG / "budget_example.gif", size=(10, 4.4))
to_gif(test_chart, IMG / "test_results.gif", size=(9.6, 4.6))
(ROOT / "docs" / "test_counts.json").unlink()


# ------------------------------------------------------------------ animated SVG tables
def svg_table(title, subtitle, header, rows, widths, aligns, path, red_cols=()):
    pad, rh = 14, 30
    width = sum(widths) + 2 * pad
    top = 70
    height = top + rh * (len(rows) + 1) + 24
    n = len(rows)
    cycle = 6 + 0.35 * n
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{title}">',
           "<style>.t{font:13px Helvetica,Arial,sans-serif;fill:#1b2a41}.h{font:700 13px Helvetica,Arial,sans-serif;fill:#fff}.ttl{font:700 19px Helvetica,Arial,sans-serif;fill:#1F3A5F}"
           ".sub{font:12px Helvetica,Arial,sans-serif;fill:#5b6b82}.neg{fill:#B3261E}.tot{font-weight:700}"
           f".row{{opacity:0;animation:rowin {cycle}s ease-out infinite}}"
           "@keyframes rowin{0%{opacity:0;transform:translateX(-36px)}5%{opacity:1;transform:none}86%{opacity:1;transform:none}96%,100%{opacity:0;transform:translateX(18px)}}"
           ".hl{animation:glow 3s ease-in-out infinite}@keyframes glow{0%,100%{opacity:.0}50%{opacity:.18}}</style>",
           f'<rect width="{width}" height="{height}" rx="12" fill="#F6F8FB" stroke="#C5CCD6"/>',
           f'<text class="ttl" x="{pad + 4}" y="30">{xesc(str(title))}</text><text class="sub" x="{pad + 4}" y="50">{xesc(str(subtitle))}</text>',
           f'<rect x="{pad}" y="{top - 6}" width="{width - 2 * pad}" height="{rh - 4}" rx="6" fill="#1F3A5F"/>']

    def xpos(j):
        x = pad + sum(widths[:j])
        return x + widths[j] - 10 if aligns[j] == "r" else x + 10

    for j, h in enumerate(header):
        anchor = "end" if aligns[j] == "r" else "start"
        out.append(f'<text class="h" x="{xpos(j)}" y="{top + 13}" text-anchor="{anchor}">{xesc(str(h))}</text>')
    for i, r in enumerate(rows):
        y = top + rh * (i + 1)
        delay = f"{0.35 * (i + 1):.2f}s"
        bg = "#EEF2F7" if i % 2 == 0 else "#FFFFFF"
        is_tot = str(r[0]).upper() == "TOTAL"
        g = [f'<g class="row" style="animation-delay:{delay}"><rect x="{pad}" y="{y - 6}" width="{width - 2 * pad}" height="{rh - 2}" rx="4" fill="{bg}"/>']
        for j, c in enumerate(r):
            anchor = "end" if aligns[j] == "r" else "start"
            cls = "t" + (" tot" if is_tot else "") + (" neg" if (j in red_cols and str(c).startswith("-")) else "")
            g.append(f'<text class="{cls}" x="{xpos(j)}" y="{y + 13}" text-anchor="{anchor}">{xesc(str(c))}</text>')
        g.append("</g>")
        out.append("".join(g))
    out.append("</svg>")
    path.write_text("\n".join(out), encoding="utf-8")
    print(path.name)


svg_table("Cost of the reference trip at every destination", "2 travellers, 3 days / 2 nights, Standard, from Islamabad (PKR)",
          ["Destination", "Transport", "Accommodation", "Food", "Total", "Per person"],
          [[n, f"{b.transportation:,}", f"{b.accommodation:,}", f"{b.food:,}", f"{b.total:,}", f"{b.cost_per_person:,.2f}"] for n, b in comps],
          [150, 120, 140, 110, 120, 120], ["l", "r", "r", "r", "r", "r"], IMG / "table_destination_costs.svg")
svg_table("Ranked alternatives for the over-budget Hunza trip", "Budget PKR 150,000 - every alternative is fully recalculated and fits the budget",
          ["#", "Alternative", "Complete cost", "Remaining", "Score"],
          [[i, a.label, format_pkr(a.breakdown.total), format_pkr(scenario.budget - a.breakdown.total), a.score] for i, a in enumerate(ranked, 1)],
          [40, 330, 130, 120, 80], ["l", "l", "r", "r", "r"], IMG / "table_ranked_alternatives.svg")
svg_table("Monthly budget: planned vs actual", "Home & Kitchen, November 2026, available PKR 120,000",
          ["Category", "Planned", "Actual", "Difference"],
          [[c, format_pkr(p), format_pkr(a), format_pkr(d)] for c, p, a, d in brows],
          [250, 140, 140, 140], ["l", "r", "r", "r"], IMG / "table_budget_summary.svg", red_cols=(3,))


# ------------------------------------------------------------------ PDF page slideshows (cross-fade, looping)
def slideshow(pngs, gif, width=520, hold=1900, fade=5):
    ims = []
    for p in pngs:
        im = Image.open(p).convert("RGB")
        ims.append(im.resize((width, round(im.height * width / im.width)), Image.LANCZOS))
    h = max(i.height for i in ims)
    canvases = []
    for im in ims:
        c = Image.new("RGB", (width, h), (255, 255, 255))
        c.paste(im, (0, 0))
        canvases.append(c)
    frames, times = [], []
    for k, im in enumerate(canvases):
        frames.append(im)
        times.append(hold)
        nxt = canvases[(k + 1) % len(canvases)]
        for s in range(1, fade):
            frames.append(Image.blend(im, nxt, s / fade))
            times.append(60)
    pal = [f.quantize(colors=160, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    pal[0].save(gif, save_all=True, append_images=pal[1:], duration=times, loop=0, optimize=True)
    print(gif.name, f"{gif.stat().st_size // 1024} KB")


SHOT = ROOT / "docs" / "screenshots"
slideshow([SHOT / "trip-1.png", SHOT / "trip-2.png", SHOT / "budget-1.png"], IMG / "pdf_reportlab_slideshow.gif")
slideshow([SHOT / "demo_pdf_trip.png", SHOT / "demo_pdf_budget.png"], IMG / "pdf_demo_slideshow.gif")
