"""Render the three-page technical report from the frozen release and saved model."""
import json
from pathlib import Path
import sys

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from data_generation.config import ROOT

INK = "#182b31"
REPORT_TITLE = "Shipment ETA Prediction System — Technical Report"
REPORT_PATH = ROOT / "reports" / "Shipment ETA Prediction System - Technical Report.pdf"
TEAL = "#30585c"
MUTE = "#506569"
styles = {
    name: ParagraphStyle(
        name,
        fontName=font,
        fontSize=size,
        leading=leading,
        textColor=colors.HexColor(color),
        spaceAfter=space,
    )
    for name, font, size, leading, color, space in [
        ("title", "Helvetica-Bold", 27, 31, INK, 10),
        ("intro", "Helvetica", 12, 17, TEAL, 15),
        ("h", "Helvetica-Bold", 13, 16, INK, 5),
        ("p", "Helvetica", 10, 14.6, INK, 10),
        ("note", "Helvetica", 9, 12.5, MUTE, 8),
    ]
}


def table(headers, rows, widths):
    result = Table([headers, *rows], colWidths=widths, hAlign="LEFT")
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#daeaeb")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(INK)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f1f6f5")],
                ),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return result


def render():
    from demonstrations import STAGES, read_cases

    snapshots = pd.read_csv(ROOT / "data/processed/prediction_snapshots.csv")
    manifest = pd.read_csv(ROOT / "data/processed/split_manifest.csv")
    source = ROOT / "models/tuning"
    metrics = {s: json.loads((source / s / "metrics.json").read_text()) for s in ("validation", "test")}
    freeze = json.loads((source / "freeze.json").read_text())
    if freeze["selected"] != "E0":
        raise ValueError("This report describes the approved persistence release")
    cases, reports, shipments = read_cases()
    catalog = json.loads((ROOT / "reports/demonstrations.json").read_text())
    if [sid for _, sid, _ in cases] != [g["id"] for g in catalog]:
        raise ValueError("Refresh the demonstration catalog with scripts/demonstrations.py")
    story = []

    def p(text, style="p"):
        story.append(Paragraph(text, styles[style]))

    def grid(headers, rows, widths):
        story.extend([table(headers, rows, widths), Spacer(1, 13)])

    def clock(value):
        return pd.Timestamp(value).strftime("%d %b %H:%M:%S")

    def page(canvas, doc):
        w, h = A4
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#ddc830"))
        canvas.rect(46, h - 46, 22, 4, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor(TEAL))
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(76, h - 47, "SHIPMENT ETA PREDICTION SYSTEM")
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(w - 46, h - 47, "Aiqon AI internship submission")
        canvas.setStrokeColor(colors.HexColor("#c6d5d6"))
        canvas.line(46, 45, w - 46, 45)
        canvas.setFont("Helvetica", 8.5)
        canvas.drawString(46, 31, "Technical report   /   Synthetic shipment journeys")
        canvas.drawRightString(w - 46, 31, f"{doc.page} / 3")
        canvas.restoreState()

    p(REPORT_TITLE, "title")
    p("A receiver needs to plan an inland handoff while cargo is still at sea. A late sailing can push every later milestone back, and a faster port or customs interval can recover part of that time.", "intro")
    p("The forecast at a milestone", "h")
    p("Measure the signed difference between the reported event time and its booked milestone. Carry that deviation forward to booked final delivery. A shipment reaching port four hours late receives an ETA four hours after its booked delivery. An early report can move the ETA earlier.")
    p("<b>Final delay</b> = actual final delivery minus scheduled final delivery.<br/><b>Predicted ETA</b> = scheduled final delivery plus predicted final delay. The simulator accumulates physical stage durations to obtain actual delivery.")
    p("What the simulator represents", "h")
    p("Synthetic journeys give each shipment a known outcome even when tracking messages are missing. Five routes carry 250 consignments on 50 voyages. Departure, port arrival, processing completion, customs clearance and inland delivery follow a fixed booking. Departure shocks, weather and congestion affect a whole voyage. Cargo handling, inspections and inland travel also vary by consignment.")
    p("What a historical forecast can see", "h")
    p("Random masks suppress shared port arrivals by voyage and handling or customs reports by shipment. Messages and sensors have release clocks. The 28 inputs combine route and cargo, planned transit and remaining time, milestone progress, visible delays, recovery, weather, congestion and gap indicators. Booked stage times give the planned handling interval. Measured handling time needs both boundary reports. This distinction helps separate a long planned stop from an overrun.")
    grid(["Fixed partition", "Voyages", "Shipments", "Pre-delivery forecasts"],
          [[s.title(), m.voyage_id.nunique(), len(m), snapshots.shipment_id.isin(m.shipment_id).sum()]
           for s in ("train","validation","test") for m in [manifest.loc[manifest.split.eq(s)]]],
          [135, 85, 105, 160])
    p("From event to screen", "h")
    p("FastAPI supplies the React application with event-time forecasts and evidence. Dashboard identifies attention cases, Shipments replays a consignment, Delay Analysis shows observed intervals, and Model Performance compares the fixed evaluations. Rule-based risk is low at or below 2 h, moderate above 2 through 6 h and high above 6 h.")
    story.append(PageBreak())
    p("Why persistence is the default", "title")
    p("The latest deviation summarizes delay already accumulated along the route. A residual model must predict the additional change after that observation.", "intro")
    p("Grouped tuning and validation selection", "h")
    p("The original Random Forest averages tree estimates of final delay. XGBoost and CatBoost learn the residual (final delay minus current deviation) and add their estimate back to the observed deviation. Imputation and encoding use training data. Three expanding training folds each scored five later voyages after earlier delivery labels were available. A preceding block supported early stopping. Each of the two boosters and the comparison forest had 100 tuning trials.")
    p("A learned candidate had to improve validation MAE without increasing severe-delay shortfall. Persistence had the lowest validation MAE and was frozen before this test comparison. <b>The held-out test set had been inspected previously during development.</b>")
    names = {"E0":"Persistence", "E1":"Original forest", "T1":"Tuned XGBoost", "T2":"Tuned CatBoost"}
    def pair(key, *fields):
        values = []
        for split in ("validation", "test"):
            v = metrics[split][key]
            for field in fields:
                v = v[field]
            values.append(f"{v:.2f}")
        return " / ".join(values)
    p("Validation / held-out test. Error and shortfall are in hours.", "note")
    grid(["Candidate", "MAE", "RMSE", "R-squared", "P90 abs.", "Shortfall"],
          [[name, pair(k,"mae"), pair(k,"rmse"), pair(k,"r2"), pair(k,"p90"), pair(k,"severe","mean_under")]
           for k,name in names.items()], [99, 75, 75, 73, 80, 83])
    p("Large errors and operational use", "h")
    p("Severe shortfall averages max(actual delay minus forecast delay, 0) among reports from shipments finishing over six hours late. A residual booster can shift the forecast toward larger downstream delays, reducing squared error and severe misses while raising overall MAE. The severe cohort has 11 validation shipments and 10 test shipments.")
    v, t = (metrics[s]["E0"] for s in ("validation", "test"))
    p(f"Persistence was within four, six and eight hours on {v['within_4_pct']:.1f}%, {v['within_6_pct']:.1f}% and {v['within_8_pct']:.1f}% of validation reports. On test the figures were {t['within_4_pct']:.1f}%, {t['within_6_pct']:.1f}% and {t['within_8_pct']:.1f}%. Its median absolute error was {pair('E0','median')} h.", "note")
    p("How to read an explanation", "h")
    p("A released deviation or measured duration is operational evidence. Forest decision paths and booster SHAP values explain individual model estimates. Global importance summarizes influence across observations. Correlated inputs can share influence, so model associations alone cannot establish the physical cause of a delay.")
    story.append(PageBreak())
    p("Reading a journey", "title")
    _, sid, _ = cases[0]
    s = shipments.loc[sid]
    journey_reports = reports[reports.shipment_id.eq(sid)].sort_values("event_available_at")
    p(f"{sid} on voyage {s.voyage_id} travelled from {s.origin} via {s.destination_port} to {s.final_destination}. Each row shows what an operator could know as that report arrived. Clocks are UTC.", "intro")
    grid(["Report", "Released at", "Deviation (h)", "Revision (h)", "Final ETA"],
          [[STAGES[r.stage_order], clock(r.event_available_at), f"{r.E0_hours:+.2f}",
            "Initial" if pd.isna(r.change) else f"{r.change:+.2f}", clock(r.E0_eta)] for r in journey_reports.itertuples()],
          [100, 105, 80, 80, 120])
    proc = journey_reports[journey_reports.stage_order.eq(2)].iloc[0]
    p(f"Port processing took {proc.processing_hours:.2f} h. The shipment moved from {proc.E0_hours - proc.change:.2f} h late at port arrival to {proc.E0_hours:.2f} h late after handling. The {proc.change:.2f} h increase moved the ETA later by the same interval. The two stage deviations are cumulative balances.")
    p(f"<b>Completed-journey reveal.</b> Delivery occurred on {clock(s.actual_arrival)} UTC, {s.final_delay_hours:.2f} h after booking. Its last pre-delivery forecast was {clock(journey_reports.iloc[-1].E0_eta)} UTC.", "note")
    p("Two more held-out illustrations", "h")
    _, rec_id, rec = cases[1]
    _, gap_id, gap = cases[2]
    p(f"<b>{rec_id} | Partial recovery.</b> {STAGES[rec.stage_order]} recovered {-rec.change:.2f} h since the preceding report. The shipment still ran {rec.stage_delay_hours:.2f} h late.<br/>"
      f"<b>{gap_id} | Missing tracking.</b> The {STAGES[gap.stage_order].lower()} report revealed {int(gap.gap)} skipped reports. The deviation change of {gap.change:+.2f} h covers the full observed interval. Each individual stage's share is unknown.")
    p("What paired observations support", "h")
    handling = snapshots[snapshots.snapshot_stage.eq("port_processing_complete")].dropna(subset=["observed_congestion_level", "known_port_processing_hours"])
    calls = handling.groupby("voyage_id")[["observed_congestion_level","known_port_processing_hours"]].mean()
    r = calls.iloc[:,0].corr(calls.iloc[:,1])
    p(f"Across {len(calls)} voyages with both measurements at a handling report, the Pearson correlation between port congestion and average observed processing duration was {r:.2f}. Each voyage counts once. This reflects the simulator's congestion penalty and the observed mix of cargo and routes.")
    p("Limits and next steps", "h")
    p(f"Persistence explains little of the held-out variance (R² = {t['r2']:.2f}). The cohort is small and synthetic, with five validation voyages and ten test voyages. Reports from the same sailing are correlated. Future disruptions are unobserved. Independent carrier data are needed to validate performance and calibrate alert probabilities.")
    p("Evidence: frozen split manifest and report logs, models/tuning split metrics and predictions, and reports/demonstration_guide.md.", "note")
    doc = SimpleDocTemplate(str(REPORT_PATH), pagesize=A4,
                            leftMargin=46, rightMargin=46, topMargin=66, bottomMargin=55,
                            title=REPORT_TITLE, author="Shipment ETA Prediction System")
    doc.build(story, onFirstPage=page, onLaterPages=page)


if __name__ == "__main__":
    render()
