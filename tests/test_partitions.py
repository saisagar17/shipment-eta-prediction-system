"""Time-of-knowledge boundaries, including delayed delivery reports and early sailings."""
import pandas as pd
import pytest

from data_generation.snapshots import split_manifest


def small_cohort():
    times = pd.date_range("2025-01-01", periods=10, freq="D", tz="UTC")
    voyages = pd.DataFrame({"voyage_id": list("ABCDEFGHIJ"), "scheduled_departure": times,
                            "actual_departure": times})
    ships = pd.DataFrame({"shipment_id": [f"S{i}" for i in range(10)], "voyage_id": voyages.voyage_id,
                          "actual_arrival": times + pd.Timedelta(hours=6)})
    reports = pd.DataFrame({"shipment_id": ships.shipment_id, "stage_order": 4,
                            "event_available_at": ships.actual_arrival})
    return ships, voyages, reports


def test_late_report_from_earlier_voyage_blocks_nominal_cut():
    ships, voyages, reports = small_cohort()
    baseline = split_manifest(ships, voyages, reports)
    assert list(baseline.split).count("train") == 7
    # A second consignment on F reports at H's departure. Strict eligibility excludes that cut.
    extra = ships.iloc[[5]].assign(shipment_id="extra")
    ships = pd.concat([ships, extra], ignore_index=True)
    reports.loc[len(reports)] = ["extra", 4, voyages.actual_departure.iloc[7]]
    manifest = split_manifest(ships, voyages, reports).set_index("voyage_id")
    assert manifest.loc["F", "split"].nunique() == 1
    assert manifest.loc["F", "split"].iloc[0] == manifest.loc["H", "split"]


def test_early_evaluation_departure_blocks_boundary():
    ships, voyages, reports = small_cohort()
    voyages.loc[7, "actual_departure"] = ships.actual_arrival.iloc[6] - pd.Timedelta(minutes=1)
    manifest = split_manifest(ships, voyages, reports).set_index("voyage_id")
    assert manifest.loc["G","split"] == manifest.loc["H","split"]


def test_no_feasible_cut_fails_explicitly():
    ships, voyages, reports = small_cohort()
    reports.loc[0, "event_available_at"] = ships.actual_arrival.max()
    with pytest.raises(ValueError, match="No pair of label-complete"):
        split_manifest(ships, voyages, reports)


def test_reference_partitions_are_contiguous_and_label_complete(tables):
    manifest = tables["split_manifest"]
    fleet = tables["vessel_voyages"].sort_values("scheduled_departure")
    split_by_voyage = manifest.groupby("voyage_id").split
    assert split_by_voyage.nunique().eq(1).all()
    partition = fleet.voyage_id.map(split_by_voyage.first())
    assert partition.map({"train": 0, "validation": 1, "test": 2}).is_monotonic_increasing
    snapshots = tables["prediction_snapshots"].merge(manifest, on=["shipment_id","voyage_id"],
                                                     how="left", validate="many_to_one")
    assert snapshots.split.notna().all() and snapshots.groupby("shipment_id").split.nunique().eq(1).all()
    delivery = tables["milestones"].query("stage_order == 4").merge(manifest, on="shipment_id")
    for earlier in [{"train"}, {"train","validation"}]:
        latest = delivery.loc[delivery.split.isin(earlier), "event_available_at"].max()
        later = fleet[~partition.isin(earlier)]
        assert latest < min(later.actual_departure.min(), later.scheduled_departure.min())
        assert latest < snapshots.loc[~snapshots.split.isin(earlier),"prediction_timestamp"].min()
