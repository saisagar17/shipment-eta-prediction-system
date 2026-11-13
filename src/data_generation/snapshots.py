"""Event-time feature builder. Plans, tracking messages and sensor releases are its only inputs."""
from itertools import combinations

import numpy as np
import pandas as pd

from .config import HOUR
from .schema import DELAYS, FEATURES, TARGETS, TRACE

PLAN_COLUMNS = """shipment_id voyage_id route_id cargo_type final_destination
scheduled_departure scheduled_arrival planned_duration_hours""".split()
EVENT_COLUMNS = "stage_order stage_name scheduled_timestamp actual_timestamp event_available_at".split()


def features_as_of(plan, events, sensor, timestamp):
    """Build the live feature vector for one shipment, or None before departure/after delivery.

    plan is a mapping. events and sensor are attribute-accessible records for the same
    shipment and voyage respectively. A full replay log or its as-of prefix gives the same result.
    """
    visible = {e.stage_order: e for e in events
               if pd.notna(e.event_available_at) and e.event_available_at <= timestamp}
    if 0 not in visible or 4 in visible:
        return None
    orders = sorted(visible)
    last = visible[orders[-1]]
    deviations = {k: (e.actual_timestamp - e.scheduled_timestamp) / HOUR for k, e in visible.items()}
    changes = np.diff([deviations[k] for k in orders])
    start = visible[0].actual_timestamp

    def duration(first, second):
        if first in visible and second in visible:
            return (visible[second].actual_timestamp - visible[first].actual_timestamp) / HOUR
        return np.nan

    def reading(value, released):
        return value if pd.notna(released) and released <= timestamp else np.nan

    return dict(
        snapshot_stage=last.stage_name, completed_stage_count=len(visible),
        route_id=plan["route_id"], cargo_type=plan["cargo_type"], final_destination=plan["final_destination"],
        planned_duration_hours=plan["planned_duration_hours"], planned_transit_hours=plan["planned_transit_hours"],
        remaining_planned_hours=(plan["scheduled_arrival"] - timestamp) / HOUR,
        elapsed_hours=(timestamp - start) / HOUR,
        time_since_last_event_hours=(timestamp - last.actual_timestamp) / HOUR,
        departure_day_of_week=plan["scheduled_departure"].dayofweek,
        departure_month=plan["scheduled_departure"].month,
        **{name: deviations.get(k, np.nan) for k, name in enumerate(DELAYS)},
        current_stage_delay_hours=deviations[orders[-1]],
        cumulative_added_delay_hours=changes.clip(min=0).sum(),
        cumulative_recovered_hours=-changes.clip(max=0).sum(),
        observed_weather_severity=reading(sensor.weather_severity, sensor.weather_available_at),
        observed_congestion_level=reading(sensor.congestion_level, sensor.congestion_available_at),
        known_port_processing_hours=duration(1, 2), known_customs_processing_hours=duration(2, 3),
        actual_transit_hours_so_far=duration(0, 1), port_arrival_observed=1 in visible,
        port_processing_observed=2 in visible, customs_observed=3 in visible,
        missing_event_count=orders[-1] + 1 - len(orders))


def build_snapshots(plans, observations, measurements):
    """Replay report arrivals. Caller supplies an allowlisted planning view without outcomes."""
    logs = {sid: list(group[EVENT_COLUMNS].itertuples(index=False))
            for sid, group in observations.groupby("shipment_id")}
    sensors = {s.voyage_id: s for s in measurements.itertuples(index=False)}
    rows = []
    for plan in plans.to_dict("records"):
        sid, vid = plan["shipment_id"], plan["voyage_id"]
        events = logs[sid]
        for event in events:
            at = event.event_available_at
            if event.stage_order == 4 or pd.isna(at):
                continue
            features = features_as_of(plan, events, sensors[vid], at)
            if features is not None:
                rows.append(dict(snapshot_id=f"{sid}-{event.stage_order}", shipment_id=sid,
                                 voyage_id=vid, prediction_timestamp=at, **features))
    return pd.DataFrame(rows, columns=TRACE + FEATURES).sort_values(["shipment_id", "prediction_timestamp"])


def planning_view(shipments, voyages):
    return shipments[PLAN_COLUMNS].merge(voyages[["voyage_id", "planned_transit_hours"]],
                                         validate="many_to_one", on="voyage_id")


def attach_labels(features, shipments, threshold):
    labels = shipments[["shipment_id", "final_delay_hours", "actual_arrival"]].copy()
    labels.columns = ["shipment_id", *TARGETS[:2]]
    labels[TARGETS[2]] = (labels[TARGETS[0]] > threshold).astype(int)
    return features.merge(labels, on="shipment_id", validate="many_to_one")


def split_manifest(shipments, voyages, observations):
    """Find two label-complete boundaries and allocate every scheduled voyage."""
    fleet = voyages.sort_values(["scheduled_departure", "voyage_id"]).set_index("voyage_id")
    ordered = fleet.index
    delivery_reports = observations.loc[observations.stage_order.eq(4)].set_index("shipment_id")
    released = shipments.shipment_id.map(delivery_reports.event_available_at)
    if released.isna().any() or (released < shipments.actual_arrival).any():
        raise ValueError("Every shipment needs a valid final-delivery report to assign splits")
    latest_label = released.groupby(shipments.voyage_id).max().reindex(ordered).cummax()
    # Strict cut before both scheduled and physical starts, including early departures.
    starts = fleet[["scheduled_departure", "actual_departure"]].min(axis=1)
    earliest_future = starts.iloc[::-1].cummin().iloc[::-1]
    eligible = [i for i in range(1, len(ordered)) if latest_label.iloc[i-1] < earliest_future.iloc[i]]
    if len(eligible) < 2:
        raise ValueError("No pair of label-complete boundaries for three nonempty partitions")
    counts = shipments.groupby("voyage_id").size().reindex(ordered).cumsum().to_numpy()
    def cost(pair):
        i, j = pair
        # Integer percentage units keep equal-distance ties exact.
        return abs(100*counts[i-1] - 70*len(shipments)) + abs(100*counts[j-1] - 85*len(shipments))
    first, second = min(combinations(eligible, 2), key=cost)
    partitions = dict(zip(ordered, ["train"]*first + ["validation"]*(second-first)
                          + ["test"]*(len(ordered)-second)))
    manifest = shipments[["shipment_id", "voyage_id"]].copy()
    manifest["split"] = manifest.voyage_id.map(partitions)
    return manifest
