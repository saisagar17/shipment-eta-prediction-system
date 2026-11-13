"""Create tracking and sensor feeds. Shared messages get a single mask and release time."""
import numpy as np
import pandas as pd

from .schema import MEAS, OBS


def sample_missing(keys, rate, rng):
    """Select a uniformly random subset, rounding its requested size to the nearest integer."""
    return set(rng.choice(keys, size=int(len(keys) * rate + .5), replace=False))


def observe(voyages, shipments, truth, cfg, rng):
    voyage_ids = voyages.voyage_id.to_list()
    shipment_ids = shipments.shipment_id.to_list()
    assignment = shipments.set_index("shipment_id").voyage_id.to_dict()
    arrival_gaps = sample_missing(voyage_ids, cfg.missing_event_rate, rng)
    handling_gaps = sample_missing(shipment_ids, cfg.missing_event_rate, rng)
    customs_gaps = sample_missing(shipment_ids, cfg.missing_event_rate, rng)
    weather_gaps = sample_missing(voyage_ids, cfg.missing_weather_rate, rng)
    congestion_gaps = sample_missing(voyage_ids, cfg.missing_congestion_rate, rng)

    def lag():
        return pd.Timedelta(seconds=int(rng.integers(0, 60 * cfg.max_event_lag_minutes + 1)))

    shared, sensors = {}, {}
    for v in voyages.itertuples():
        key = v.voyage_id
        shared[key] = (v.actual_departure + lag(),
                       pd.NaT if key in arrival_gaps else v.actual_port_arrival + lag())
        sensor = {"voyage_id": key}
        for field, gaps, value, release in [
            ("weather_severity", weather_gaps, v.voyage_weather_severity, "weather_available_at"),
            ("congestion_level", congestion_gaps, v.port_congestion_level, "congestion_available_at")
        ]:
            sensor[field] = np.nan if key in gaps else value
            sensor[release] = (pd.NaT if key in gaps else v.actual_port_arrival +
                               pd.Timedelta(minutes=int(rng.integers(5, 61))))
        sensors[key] = sensor

    rows = []
    for t in truth.itertuples():
        sid, k = t.shipment_id, t.stage_order
        key = assignment[sid]
        if k < 2:
            released = shared[key][k]
        elif (k == 2 and sid in handling_gaps) or (k == 3 and sid in customs_gaps):
            released = pd.NaT
        elif k == 4:
            released = t.actual_timestamp  # Immediate proof of delivery.
        else:
            released = t.actual_timestamp + lag()
        missing = pd.isna(released)
        # Interval measurements need both boundary reports. Never copy a hidden start.
        has_interval = ((k == 2 and key not in arrival_gaps) or
                        (k == 3 and sid not in handling_gaps)) and not missing
        rows.append(dict(shipment_id=sid, stage_order=k, stage_name=t.stage_name,
                         scheduled_timestamp=t.scheduled_timestamp,
                         actual_timestamp=pd.NaT if missing else t.actual_timestamp,
                         event_available_at=released, event_missing=missing,
                         stage_delay_hours=np.nan if missing else t.stage_delay_hours,
                         # Severity-derived labels belong to the physical ledger. A tracking
                         # message cannot identify rough weather before the sensor releases it.
                         disruption_type=None if missing or k in (1, 2) else t.disruption_type,
                         processing_start_timestamp=t.processing_start_timestamp if has_interval else pd.NaT,
                         processing_hours=t.processing_hours if has_interval else np.nan,
                         weather_severity=sensors[key]["weather_severity"] if k == 1 and not missing else np.nan,
                         congestion_level=sensors[key]["congestion_level"] if k == 1 and not missing else np.nan))
    return pd.DataFrame(rows, columns=OBS), pd.DataFrame(sensors.values(), columns=MEAS)
