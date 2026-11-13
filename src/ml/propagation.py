"""Observable schedule changes. The first deviation is a starting balance."""
import pandas as pd
from data_generation.config import HOUR


def milestones(events, at, actuals=None):
    historical = actuals is not None
    reported_orders = [
        e.stage_order
        for e in events
        if pd.notna(e.event_available_at) and e.event_available_at <= at
    ]
    rows = []
    previous = None
    for e in events:
        k = e.stage_order
        reported = k in reported_orders
        state = "reported" if reported else "pending"
        if historical and pd.isna(e.event_available_at):
            state = "unreported"
        elif not reported and k < max(reported_orders, default=-1):
            state = "observation_gap"
        physical = (
            actuals[k]
            if historical
            else e.actual_timestamp
            if reported and k < 4
            else None
        )
        delay = (
            (physical - e.scheduled_timestamp) / HOUR if physical is not None else None
        )
        gap = False
        change = None
        if delay is not None:
            if previous is not None:
                gap = k != previous[0] + 1
                change = delay - previous[1]
            previous = (k, delay)
        rows.append(
            dict(
                stage=e.stage_name,
                order=k,
                scheduled=e.scheduled_timestamp,
                actual=physical,
                released=e.event_available_at
                if reported and (k < 4 or historical)
                else None,
                state=state,
                deviation=delay,
                change=change,
                across_gap=gap,
                added=max(change, 0) if change is not None else None,
                recovered=max(-change, 0) if change is not None else None,
            )
        )
    return rows
