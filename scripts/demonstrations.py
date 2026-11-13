"""Select held-out replays from observed transitions, then join outcomes for explicit reveal."""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from data_generation.config import ROOT
from ml.model import eta

REPORTS = ROOT / "reports"
STAGES = ["Departure", "Port arrival", "Port processing", "Customs clearance", "Final delivery"]


def read_cases():
    # Candidate selection sees only released reports, bookings, and the fixed test assignment.
    manifest = pd.read_csv(ROOT / "data/processed/split_manifest.csv")
    held_out = manifest.loc[manifest.split == "test", ["shipment_id"]]
    events = pd.read_csv(ROOT / "data/raw/milestones.csv").merge(held_out, validate="many_to_one")
    observed = events.loc[events.stage_order.lt(4) & events.event_available_at.notna()].copy()
    observed = observed.sort_values(["shipment_id", "event_available_at"])
    groups = observed.groupby("shipment_id")
    observed["change"] = groups.stage_delay_hours.diff()
    observed["gap"] = groups.stage_order.diff() - 1
    adjacent = observed[observed.gap.eq(0) & observed.stage_delay_hours.gt(0)]
    candidates = [
        ("Delay amplification", adjacent[adjacent.stage_order.eq(2) & adjacent.change.gt(0)], "change", False),
        ("Partial delay recovery", adjacent[adjacent.stage_order.isin([2, 3]) & adjacent.change.lt(0)], "change", True),
        ("Missing intermediate tracking", observed[observed.gap.gt(0)], "gap", False),
    ]
    cases = []
    used = set()
    for kind, pool, field, ascending in candidates:
        ranked = pool.loc[~pool.shipment_id.isin(used)].sort_values(
            [field, "shipment_id", "stage_order"], ascending=[ascending, True, True]
        )
        highlight = ranked.iloc[0]
        sid = highlight.shipment_id
        used.add(sid)
        cases.append((kind, sid, highlight))
    # Only after selection, verify every report against the frozen E0 forecast at its clock.
    predictions = pd.read_csv(
        ROOT / "models/tuning/test/predictions.csv",
        usecols=["shipment_id", "prediction_timestamp", "snapshot_stage", "E0_hours", "E0_eta", "scheduled_delivery"],
    )
    observed = observed.merge(
        predictions, left_on=["shipment_id", "event_available_at", "stage_name"],
        right_on=["shipment_id", "prediction_timestamp", "snapshot_stage"], validate="one_to_one", how="outer",
        indicator=True,
    )
    if not observed["_merge"].eq("both").all():
        raise ValueError("Held-out reports and saved forecasts differ")
    np.testing.assert_allclose(observed.stage_delay_hours, observed.E0_hours, atol=1e-9, rtol=0)
    expected = pd.to_datetime([eta(t, d) for t, d in zip(observed.scheduled_delivery, observed.E0_hours)], utc=True)
    if not expected.equals(pd.DatetimeIndex(pd.to_datetime(observed.E0_eta, utc=True))):
        raise ValueError("Saved ETA disagrees with the booked delivery and the observed deviation")
    shipments = pd.read_csv(ROOT / "data/raw/shipments.csv").set_index("shipment_id")
    truth = pd.read_csv(ROOT / "data/ground_truth/ground_truth_milestones.csv")
    deliveries = truth.loc[truth.stage_order.eq(4)].set_index("shipment_id")
    for _, sid, _ in cases:
        if shipments.at[sid, "actual_arrival"] != deliveries.at[sid, "actual_timestamp"]:
            raise ValueError(f"{sid} delivery disagrees with the physical ledger")
        np.testing.assert_allclose(
            shipments.at[sid, "final_delay_hours"], deliveries.at[sid, "stage_delay_hours"],
            atol=1e-9, rtol=0,
        )
    return cases, observed, shipments


def clock(value):
    return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S")


def describe(kind, highlight):
    if kind == "Delay amplification":
        return (f"Port processing took {highlight.processing_hours:.2f} h. Between the port arrival and handling reports, "
                f"the observed deviation grew by {highlight.change:.2f} h to {highlight.stage_delay_hours:.2f} h late. "
                "The operational ETA moved later by the same interval.")
    if kind == "Partial delay recovery":
        return (f"{STAGES[highlight.stage_order]} recovered {-highlight.change:.2f} h relative to the preceding report. "
                f"The shipment was still {highlight.stage_delay_hours:.2f} h behind schedule. "
                "The operational ETA therefore moved earlier while remaining later than the booking.")
    return (f"The {STAGES[highlight.stage_order].lower()} report followed {int(highlight.gap)} missing intermediate reports. "
            f"The deviation changed by {highlight.change:+.2f} h over the full observed interval. "
            "The records cannot assign portions of that change to ocean transit, handling or customs.")


def write():
    cases, observed, shipments = read_cases()
    catalog = []
    guide = [
        "# Three held-out shipment replays",
        "These examples illustrate three observable patterns in the existing test records. The model was already frozen when "
        "the examples were chosen. All clocks are UTC. Positive deviation means late relative to the booked milestone.",
        "From Dashboard, open a demonstration shipment in Shipments. Inspect the prediction at the first released report, "
        "advance to the next released milestone and compare the revised ETA. In Delay Analysis, check the signed change "
        "and gaps. Return to shipment details for the completed-journey reveal. Model Performance shows population scores.",
        "The row clock is when the report became available. The departure row establishes the starting deviation. "
        "Subsequent rows compare with the immediately preceding **reported** stage. For persistence, the signed change in "
        "deviation and the change in issued ETA are equal. A missing report issues no update.",
    ]
    reveal = []
    for kind, sid, highlight in cases:
        reports = observed[observed.shipment_id.eq(sid)].sort_values("event_available_at")
        s = shipments.loc[sid]
        catalog.append(dict(id=sid, type=kind, as_of=reports.iloc[0].event_available_at))
        guide += [
            f"## {kind} · {sid}",
            f"{s.origin} → {s.destination_port} → {s.final_destination} · {s.voyage_id}. "
            f"Booked final delivery **{clock(s.scheduled_arrival)} UTC**.",
            "| Released at (UTC) | Observable milestone | Deviation (h) | Change / ETA revision (h) | Operational ETA (UTC) |\n"
            "|---|---|---:|---:|---|\n" + "\n".join(
                f"| {clock(m.event_available_at)} | {STAGES[m.stage_order]} | {m.stage_delay_hours:+.2f} | "
                f"{'Initial' if pd.isna(m.change) else format(m.change, '+.2f')}"
                f"{' across gap' if m.gap > 0 else ''} | {clock(m.E0_eta)} |" for m in reports.itertuples()
            ),
            describe(kind, highlight),
        ]
        reveal.append(f"| {sid} | {clock(reports.iloc[-1].E0_eta)} | {clock(s.actual_arrival)} | "
                      f"{s.final_delay_hours:+.2f} |")
    guide += [
        "## Completed-journey reveal",
        "Open this comparison after finishing the point-in-time replay. Actual final delivery is the physical inland delivery. "
        "Each final delay is actual delivery minus booked delivery. Delivery closes the journey without issuing another forecast.",
        "| Shipment | Last pre-delivery forecast (UTC) | Actual final delivery (UTC) | Final delay (h) |\n"
        "|---|---|---|---:|\n" + "\n".join(reveal),
        "## How the examples were selected",
        "Among test shipments, select the largest positive change during an observed adjacent port-processing interval ending late. "
        "Next, select the largest adjacent handling or customs recovery that still ends late. Finally, select the longest "
        "run of missing intermediate reports bounded by two reports before delivery. Use distinct IDs in this order. "
        "Ties use shipment ID and then milestone order. Selection uses released deviations and the existing split manifest. "
        "The generator joins final outcomes only after it has selected the examples.",
        "Run `python scripts/demonstrations.py` from the project root to reproduce this guide and its demonstration catalog. "
        "The script checks every held-out report against the saved persistence delay and ETA before writing either file.",
    ]
    (REPORTS / "demonstrations.json").write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    (REPORTS / "demonstration_guide.md").write_text("\n\n".join(guide) + "\n", encoding="utf-8")
    print(", ".join(d["id"] for d in catalog))


if __name__ == "__main__":
    write()
