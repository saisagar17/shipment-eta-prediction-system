from dataclasses import replace

import pandas as pd

from data_generation.config import ROOT, Config
from data_generation.pipeline import export, generate
from data_generation.schema import PATHS


def test_published_bytes_reproducible(tmp_path):
    export(Config(), tmp_path)
    files = [*PATHS.values(), "data/metadata/dataset_config.json", "data/metadata/feature_schema.json",
             "data/metadata/data_dictionary.csv", "reports/dataset_validation.md"]
    for name in files:
        assert (tmp_path/name).read_bytes() == (ROOT/name).read_bytes(), name


def test_schedule_independent_of_disruptions(tables):
    alt = generate(replace(Config(), inspection_probability=1, congestion_quadratic=15))
    original = tables["ground_truth_milestones"]
    changed = alt["ground_truth_milestones"]
    pd.testing.assert_series_equal(original.scheduled_timestamp, changed.scheduled_timestamp)
    assert not original.actual_timestamp.equals(changed.actual_timestamp)


def test_observation_masks_do_not_change_physical_truth(tables):
    full = generate(replace(Config(), missing_event_rate=0, missing_weather_rate=0, missing_congestion_rate=0))
    for name in ["shipments", "vessel_voyages", "ground_truth_milestones"]:
        pd.testing.assert_frame_equal(full[name], tables[name])
    assert len(full["prediction_snapshots"]) == 1000


def test_default_cohort_variation(tables):
    s, v, t = (tables[name] for name in ["shipments","vessel_voyages","ground_truth_milestones"])
    assert (len(s), len(v), s.route_id.nunique(), len(t)) == (250, 50, 5, 1250)
    by_route = s.groupby("route_id").final_delay_hours
    assert (by_route.min() < 0).all() and (by_route.max() > 6).all()
    assert s.final_delay_hours.abs().le(2).any()
    assert v.voyage_weather_severity.corr(v.actual_transit_hours - v.planned_transit_hours) > 0
    keys = s.set_index("shipment_id").voyage_id
    def by_voyage(stage):
        rows = t[t.stage_order.eq(stage)].set_index("shipment_id")
        return rows.processing_hours.groupby(keys)
    assert by_voyage(2).mean().corr(v.set_index("voyage_id").port_congestion_level) > 0
    assert by_voyage(3).nunique().gt(1).all()
    assert set(t.loc[t.stage_order.eq(3),"disruption_type"]) == {"routine","inspection"}
    road = t[t.stage_order.eq(4)].delay_change_hours
    assert road.lt(0).any() and road.gt(0).any()


def test_all_intermediate_reports_missing():
    tables = generate(replace(Config(), missing_event_rate=1))
    f = tables["prediction_snapshots"]
    assert len(f) == 250 and f.snapshot_stage.eq("origin_departure").all()
    assert tables["ground_truth_milestones"].actual_timestamp.notna().all()


def test_multivessel_routes_and_shared_physical_events(tables):
    v = tables["vessel_voyages"]
    s = tables["shipments"]
    ledger = tables["ground_truth_milestones"].merge(s[["shipment_id", "voyage_id"]], on="shipment_id")
    assert v.groupby("route_id").vessel_id.nunique().ge(2).all()
    assert v.vessel_id.value_counts().gt(1).all()
    for _, history in v.sort_values("actual_departure").groupby("vessel_id"):
        assert (history.actual_departure.iloc[1:].to_numpy() >
                history.actual_port_arrival.iloc[:-1].to_numpy()).all()
    for k, column in [(0, "actual_departure"), (1, "actual_port_arrival")]:
        rows = ledger[ledger.stage_order.eq(k)]
        assert rows.actual_timestamp.eq(rows.voyage_id.map(v.set_index("voyage_id")[column])).all()
    arrivals = ledger[ledger.stage_order.eq(1)]
    for field in ["weather_severity", "congestion_level"]:
        assert arrivals.groupby("voyage_id")[field].nunique().eq(1).all()


def test_outcome_bands_and_partial_recovery(tables):
    threshold = Config().significant_delay_hours
    d = tables["shipments"].final_delay_hours
    assert all(mask.any() for mask in [d.lt(-2), d.abs().le(2), d.gt(2) & d.le(threshold), d.gt(threshold)])
    t = tables["ground_truth_milestones"].sort_values(["shipment_id", "stage_order"])
    previous = t.groupby("shipment_id").stage_delay_hours.shift()
    assert ((previous > t.stage_delay_hours) & t.stage_delay_hours.gt(0)).any()
    assert ((previous < t.stage_delay_hours) & previous.gt(0)).any()
    assert tables["vessel_voyages"].voyage_disruption_type.eq("severe_departure").any()
