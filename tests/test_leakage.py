"""Counterfactual tests for the same as-of function used by the historical replay."""
import pandas as pd
import pytest

from data_generation.config import HOUR
from data_generation.schema import FEATURES, TARGETS, TRACE
from data_generation.snapshots import EVENT_COLUMNS, features_as_of, planning_view


@pytest.fixture
def stream(tables):
    m = tables["milestones"]
    # Choose an intact stream with both sensors to exercise release boundaries.
    sensors = tables["port_call_measurements"].dropna().set_index("voyage_id")
    plans = planning_view(tables["shipments"],tables["vessel_voyages"])
    for plan in plans.to_dict("records"):
        events = list(m.loc[m.shipment_id.eq(plan["shipment_id"]),EVENT_COLUMNS].itertuples(index=False))
        if all(pd.notna(e.event_available_at) for e in events) and plan["voyage_id"] in sensors.index:
            sensor = next(sensors.loc[[plan["voyage_id"]]].itertuples())
            return plan, events, sensor
    pytest.fail("Expected at least one intact stream in the reference cohort")


def test_future_and_hidden_values_cannot_change_departure_features(stream):
    plan, events, sensor = stream
    at = events[0].event_available_at
    expected = features_as_of(plan,events[:1],sensor,at)
    altered = [events[0]] + [e._replace(actual_timestamp=e.actual_timestamp+10*HOUR) for e in events[1:]]
    dirty_plan = {**plan,"actual_arrival":at+30*HOUR,"final_delay_hours":-99, "future_inspection":True}
    changed = features_as_of(dirty_plan,altered,sensor._replace(weather_severity=.999),at)
    pd.testing.assert_series_equal(pd.Series(expected),pd.Series(changed))
    assert set(expected) == set(FEATURES) and not set(FEATURES).intersection(TRACE+TARGETS)


def test_withheld_report_uses_net_observed_change(stream):
    plan, events, sensor = stream
    at = events[2].event_available_at
    # Arrival has happened, but its message comes after the handling completion.
    delayed = events.copy()
    delayed[1] = delayed[1]._replace(event_available_at=at+pd.Timedelta(minutes=1))
    f = features_as_of(plan,delayed,sensor,at)
    assert f["missing_event_count"] == 1 and f["completed_stage_count"] == 2
    assert not f["port_arrival_observed"] and pd.isna(f["actual_transit_hours_so_far"])
    assert pd.isna(f["known_port_processing_hours"]) and pd.isna(f["port_arrival_delay_hours"])
    net = f["current_stage_delay_hours"] - f["departure_delay_hours"]
    assert f["cumulative_added_delay_hours"] == max(net,0)
    assert f["cumulative_recovered_hours"] == max(-net,0)
    updated = features_as_of(plan,delayed,sensor,delayed[1].event_available_at)
    assert updated["missing_event_count"] == 0 and updated["port_arrival_observed"]
    assert updated["snapshot_stage"] == events[2].stage_name


def test_sensor_release_inclusive_and_independent(stream):
    plan, events, sensor = stream
    at = events[2].event_available_at
    sensor = sensor._replace(weather_available_at=at,congestion_available_at=at+HOUR)
    before = features_as_of(plan,events,sensor,at-pd.Timedelta(seconds=1))
    now = features_as_of(plan,events,sensor,at)
    assert pd.isna(before["observed_weather_severity"])
    assert now["observed_weather_severity"] == sensor.weather_severity
    assert pd.isna(now["observed_congestion_level"])


def test_future_or_missing_event_indistinguishable_at_cutoff(stream):
    plan, events, sensor = stream
    at = events[1].actual_timestamp-pd.Timedelta(seconds=1)
    expected = features_as_of(plan,events,sensor,at)
    absent = events.copy()
    absent[1] = absent[1]._replace(actual_timestamp=pd.NaT,event_available_at=pd.NaT)
    actual = features_as_of(plan,absent,sensor,at)
    pd.testing.assert_series_equal(pd.Series(expected),pd.Series(actual))
    assert actual["missing_event_count"] == 0


def test_no_features_before_departure_or_at_delivery(stream):
    plan, events, sensor = stream
    assert features_as_of(plan,events,sensor,events[0].event_available_at-pd.Timedelta(seconds=1)) is None
    assert features_as_of(plan,events,sensor,events[-1].actual_timestamp) is None


def test_future_route_outcomes_cannot_change_feature_rows(tables):
    from data_generation.snapshots import build_snapshots

    s = tables["shipments"].copy()
    v = tables["vessel_voyages"].copy()
    # Poison later shipments' labels, route outcome aggregates, IDs used only for
    # tracing vessel identity, and realized maritime fields in the historical tables.
    future = s.scheduled_departure.gt(s.scheduled_departure.median())
    s.loc[future, "final_delay_hours"] += 1000
    s.loc[future, "actual_arrival"] += pd.Timedelta(days=42)
    s["route_mean_delay"] = s.groupby("route_id").final_delay_hours.transform("mean")
    v["vessel_id"] = "replacement"
    v["voyage_weather_severity"] = 1.0
    v["voyage_disruption_type"] = "future_disruption"
    rebuilt = build_snapshots(planning_view(s, v), tables["milestones"], tables["port_call_measurements"])
    expected = tables["prediction_snapshots"][TRACE + FEATURES]
    pd.testing.assert_frame_equal(rebuilt.reset_index(drop=True), expected.reset_index(drop=True))
    assert not {"shipment_id", "voyage_id", "snapshot_id", "vessel_id", "route_mean_delay",
                "actual_arrival", "voyage_disruption_type"}.intersection(FEATURES)
