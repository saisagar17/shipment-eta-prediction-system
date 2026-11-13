"""Descriptive cohort relationships using only reports released at the replay clock."""
from collections import defaultdict
from statistics import correlation, mean, median

import pandas as pd

from data_generation.config import HOUR, STAGES


def summarize_interactions(plans, events, sensors, at):
    """Describe the held-out replay fleet without joining simulation truth or delivery times."""
    call_durations = defaultdict(list)
    route_delays = defaultdict(list)
    departure_groups = {"Late departure": [], "On time or early": []}
    recoveries = {2: [], 3: []}
    reached = {k: 0 for k in (1, 2, 3)}
    gaps = dict.fromkeys(reached, 0)
    started = 0

    for sid, plan in plans.items():
        visible = {
            event.stage_order: event
            for event in events[sid]
            if pd.notna(event.event_available_at) and event.event_available_at <= at
        }
        if not visible:
            continue
        started += 1
        furthest = max(visible)
        for order in reached:
            if furthest >= order:
                reached[order] += 1
                gaps[order] += int(order not in visible)

        # A reported delivery can establish a preceding report gap. Its physical time
        # is deliberately excluded from these operational cohort statistics.
        deviation = {
            k: (e.actual_timestamp - e.scheduled_timestamp) / HOUR
            for k, e in visible.items() if k < 4
        }
        voyage = plan["voyage_id"]
        if 1 in visible and 2 in visible:
            duration = (visible[2].actual_timestamp - visible[1].actual_timestamp) / HOUR
            call_durations[voyage].append(duration)
        if 2 in deviation:
            route_delays[plan["route_id"]].append((voyage, deviation[2]))
        if 0 in deviation and 3 in deviation:
            group = "Late departure" if deviation[0] > 0 else "On time or early"
            departure_groups[group].append(deviation[3] - deviation[0])

        for order in recoveries:
            if order in deviation and order - 1 in deviation:
                before = max(deviation[order - 1], 0)
                after = max(deviation[order], 0)
                recoveries[order].append(max(before - after, 0))

    calls = []
    for voyage, durations in sorted(call_durations.items()):
        sensor = sensors[voyage]
        if (pd.notna(sensor.congestion_available_at) and sensor.congestion_available_at <= at
                and pd.notna(sensor.congestion_level)):
            calls.append(dict(voyage=voyage, congestion=float(sensor.congestion_level),
                              processing_hours=mean(durations), pairs=len(durations)))

    indices = [call["congestion"] for call in calls]
    durations = [call["processing_hours"] for call in calls]
    pearson = None
    if len(calls) >= 3 and len(set(indices)) > 1 and len(set(durations)) > 1:
        pearson = correlation(indices, durations)
    return {
        "as_of": at,
        "observed_shipments": started,
        "port_calls": calls,
        "port_correlation": pearson,
        "departure_groups": [
            dict(group=group, shipments=len(changes),
                 mean_change_hours=mean(changes) if changes else None,
                 increased=sum(change > 0 for change in changes))
            for group, changes in departure_groups.items()
        ],
        "routes": [
            dict(route=route, shipments=len(rows), voyages=len({v for v, _ in rows}),
                 median_hours=median(d for _, d in rows), min_hours=min(d for _, d in rows),
                 max_hours=max(d for _, d in rows))
            for route, rows in sorted(route_delays.items())
        ],
        "recovery": [
            dict(stage=STAGES[k], pairs=len(values), recovered=sum(h > 0 for h in values),
                 mean_recovered_hours=mean(values) if values else None)
            for k, values in recoveries.items()
        ],
        "gaps": [dict(stage=STAGES[k], missing=gaps[k], reached=reached[k]) for k in reached],
    }
