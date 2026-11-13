"""Release-time, denominator and interval contracts for fleet-level summaries."""
from collections import namedtuple

import pandas as pd
import pytest

from backend.interactions import summarize_interactions

Event = namedtuple("Event", "stage_order scheduled_timestamp actual_timestamp event_available_at")
Sensor = namedtuple("Sensor", "congestion_level congestion_available_at")
START = pd.Timestamp("2025-01-01T00:00:00Z")
HOUR = pd.Timedelta(hours=1)


def event(order, deviation, release):
    scheduled = START + order * 10 * HOUR
    return Event(order, scheduled, scheduled + deviation * HOUR, START + release * HOUR)


def test_pairs_and_stage_denominators_use_only_released_fields():
    plans = {
        sid: {"voyage_id": "V1", "route_id": "R1"}
        for sid in ["A", "B"]
    }
    events = {
        "A": [event(0, 2, 3), event(1, 4, 15), event(2, -1, 20), event(3, 4, 35)],
        "B": [event(0, 0, 1), event(1, 4, 15), event(2, 2, 23), event(3, 1, 45)],
    }
    sensor = {"V1": Sensor(.7, START + 30 * HOUR)}

    def run(h):
        return summarize_interactions(plans, events, sensor, START + h * HOUR)

    assert run(0)["observed_shipments"] == 0
    assert run(24)["port_calls"] == []
    snapshot = run(35)
    assert snapshot["port_calls"] == [
        {"voyage": "V1", "congestion": .7, "processing_hours": 6.5, "pairs": 2}
    ]
    assert snapshot["port_correlation"] is None
    assert snapshot["routes"] == [
        {"route": "R1", "shipments": 2, "voyages": 1, "median_hours": .5, "min_hours": -1, "max_hours": 2}
    ]
    # A went from 4h late to 1h early. Only 4h of prior lateness could be recovered.
    assert snapshot["recovery"][0]["mean_recovered_hours"] == pytest.approx(3)
    assert snapshot["departure_groups"][0]["mean_change_hours"] == 2
    assert snapshot["departure_groups"][1]["mean_change_hours"] is None
    assert run(45)["departure_groups"][1]["mean_change_hours"] == 1
    assert run(45)["recovery"][1]["pairs"] == 2
    assert run(45)["recovery"][1]["mean_recovered_hours"] == .5


def test_missing_intermediate_report_excludes_interval_and_delivery_truth():
    plans = {"A": {"voyage_id": "V1", "route_id": "R1"}}
    events = {"A": [event(0, 1, 2), event(2, 7, 28), event(4, 2, 43)]}
    sensors = {"V1": Sensor(.8, START)}
    summary = summarize_interactions(plans, events, sensors, START + 50 * HOUR)
    assert summary["gaps"] == [
        {"stage": "port_arrival", "missing": 1, "reached": 1},
        {"stage": "port_processing_complete", "missing": 0, "reached": 1},
        {"stage": "customs_clearance_complete", "missing": 1, "reached": 1},
    ]
    assert not summary["port_calls"]
    assert all(row["pairs"] == 0 for row in summary["recovery"])
    # The release of delivery establishes the customs gap. Its truth is never read.
    events["A"][-1] = events["A"][-1]._replace(actual_timestamp=None)
    assert summarize_interactions(plans, events, sensors, START + 50 * HOUR) == summary
