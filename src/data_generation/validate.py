"""Independent audit of published tables, including an as-of join for every snapshot."""
import numpy as np
import pandas as pd

from .config import HOUR, ROUTES, STAGES
from .metadata import NULLABLE, dtype_unit
from .schema import DELAYS, FEATURES, TABLES, TARGETS, TRACE
from .snapshots import split_manifest


class IntegrityError(ValueError):
    """A published dataset violates a named invariant."""


def check(condition, message):
    if not bool(condition):
        raise IntegrityError(message)


def same(left, right, label):
    """Strict shape, missingness and value comparison, allowing CSV rounding only."""
    left = pd.Series(left).reset_index(drop=True)
    right = pd.Series(right).reset_index(drop=True)
    check(len(left) == len(right) and left.isna().equals(right.isna()), label)
    if pd.api.types.is_numeric_dtype(left):
        ok = np.allclose(left, right, rtol=0, atol=1e-8, equal_nan=True)
    else:
        ok = left.fillna("<missing>").eq(right.fillna("<missing>")).all()
    check(ok, label)


def audit_snapshots(s, v, o, m, f, cfg):
    # Independent wide as-of audit. Use only reports physically published by each cutoff.
    ship = s.set_index("shipment_id").loc[f.shipment_id].reset_index()
    voy = v.set_index("voyage_id").loc[ship.voyage_id].reset_index()
    sensor = m.set_index("voyage_id").loc[ship.voyage_id].reset_index()
    f = f.reset_index(drop=True)
    at = f.prediction_timestamp
    expected = o[(o.stage_order < 4) & o.event_available_at.notna()].merge(
        s[["shipment_id", "actual_arrival"]], on="shipment_id")
    expected = expected[expected.event_available_at < expected.actual_arrival]
    def keys(df, time, stage):
        return set(zip(df.shipment_id, df[time], df[stage]))
    check(f.snapshot_id.is_unique and len(f) == len(expected) and
          keys(f, "prediction_timestamp", "snapshot_stage") == keys(expected, "event_available_at", "stage_name"),
          "exactly one snapshot per eligible trigger")
    check((at < ship.actual_arrival).all(), "snapshot before physical final delivery")
    for col in ["voyage_id", "route_id", "cargo_type", "final_destination", "planned_duration_hours"]:
        same(f[col], ship[col], "snapshot plan " + col)
    same(f.planned_transit_hours, voy.planned_transit_hours, "snapshot planned ocean duration")
    same(f.remaining_planned_hours, (ship.scheduled_arrival - at)/HOUR, "remaining schedule")
    same(f.departure_day_of_week, ship.scheduled_departure.dt.dayofweek, "scheduled weekday")
    same(f.departure_month, ship.scheduled_departure.dt.month, "scheduled month")
    times, delays, flags = {}, {}, {}
    for k in range(4):
        event = o[o.stage_order == k].set_index("shipment_id").loc[f.shipment_id].reset_index()
        flags[k] = event.event_available_at.le(at)
        times[k] = event.actual_timestamp.where(flags[k])
        delays[k] = (times[k] - event.scheduled_timestamp) / HOUR
        same(f[DELAYS[k]], delays[k], "as-of stage deviation " + STAGES[k])
    count = pd.DataFrame(flags).sum(axis=1)
    orders = f.snapshot_stage.map(dict(zip(STAGES, range(5))))
    same(f.completed_stage_count, count, "reported stage count")
    same(f.missing_event_count, orders + 1 - count, "as-of tracking gaps")
    for k, name in enumerate(["port_arrival_observed", "port_processing_observed", "customs_observed"], 1):
        same(f[name], flags[k], "availability " + name)
    for k, name in enumerate(["actual_transit_hours_so_far", "known_port_processing_hours",
                              "known_customs_processing_hours"], 1):
        same(f[name], (times[k] - times[k-1])/HOUR, "as-of interval " + name)
    same(f.elapsed_hours, (at-times[0])/HOUR, "elapsed since observed departure")
    same(f.time_since_last_event_hours, (at-pd.DataFrame(times).max(axis=1))/HOUR, "report age")
    path = pd.DataFrame(delays).ffill(axis=1)
    same(f.current_stage_delay_hours, path.iloc[:, -1], "current deviation")
    changes = path.diff(axis=1)
    same(f.cumulative_added_delay_hours, changes.clip(lower=0).sum(axis=1), "observable additions")
    same(f.cumulative_recovered_hours, -changes.clip(upper=0).sum(axis=1), "observable recoveries")
    for name, clock in [("weather_severity", "weather_available_at"),
                        ("congestion_level", "congestion_available_at")]:
        same(f["observed_" + name], sensor[name].where(sensor[clock].le(at)), "sensor release " + name)
    for target, values in zip(TARGETS, [ship.final_delay_hours, ship.actual_arrival,
                                        ship.final_delay_hours.gt(cfg.significant_delay_hours).astype(int)]):
        same(f[target], values, "label " + target)
    check(not set(FEATURES) & set(TRACE + TARGETS) and len(set(FEATURES)) == len(FEATURES),
          "approved features exclude identifiers, clocks and labels")


def validate(tables, cfg):
    v, s, t, o, m, f, p = [tables[key].reset_index(drop=True) for key in TABLES]
    for name, columns in TABLES.items():
        frame = tables[name]
        check(list(frame) == columns, "column contract " + name)
        for col in columns:
            values = frame[col]
            if col not in NULLABLE.get(name, set()):
                check(values.notna().all(), "required values " + name + "." + col)
            if not values.notna().any():
                continue
            kind, _ = dtype_unit(col)
            if kind == "datetime":
                valid_type = isinstance(values.dtype, pd.DatetimeTZDtype) and str(values.dt.tz) == "UTC"
            elif kind == "float":
                valid_type = (pd.api.types.is_numeric_dtype(values) and
                              np.isfinite(values.dropna().to_numpy()).all())
            elif kind == "integer":
                valid_type = pd.api.types.is_integer_dtype(values)
            elif kind == "boolean":
                valid_type = pd.api.types.is_bool_dtype(values)
            else:
                valid_type = pd.api.types.infer_dtype(values, skipna=True) == "string"
            check(valid_type, "dictionary type " + name + "." + col)
    check(len(v) == cfg.rounds * 5 and len(s) == cfg.rounds * 25, "shipment and voyage count")
    for frame, key in [(v, "voyage_id"), (s, "shipment_id"), (m, "voyage_id"), (p, "shipment_id")]:
        check(frame[key].is_unique and frame[key].notna().all(), "unique nonnull key " + key)
    check(set(v.voyage_id) == set(s.voyage_id) == set(m.voyage_id), "voyage foreign keys")
    check(s.groupby("voyage_id").size().between(4, 6).all(), "voyage cargo count")
    check(s.shipment_status.eq("completed").all() and s.notna().all().all() and v.notna().all().all(),
          "complete historical voyage and shipment records")
    route_map = {r.route_id: r for r in ROUTES}
    check(set(v.route_id) == set(route_map), "five designed routes")
    for row in v.itertuples():
        route = route_map[row.route_id]
        check((row.origin_port, row.destination_port) == (route.origin, route.port), "route geography")
        check(route.ocean*(1-cfg.ocean_variation)-.001 <= row.planned_transit_hours <=
              route.ocean*(1+cfg.ocean_variation)+.001, "planned ocean duration within route range")
    by_ship = v.set_index("voyage_id").loc[s.voyage_id].reset_index()
    for col, orig in [("scheduled_departure", "scheduled_departure"), ("actual_departure", "actual_departure"),
                      ("origin", "origin_port"), ("destination_port", "destination_port"), ("route_id", "route_id")]:
        same(s[col], by_ship[orig], "shared voyage " + col)
    same(s.final_destination, s.route_id.map({r.route_id: r.destination for r in ROUTES}), "inland destination")
    for col, a, b in [("planned_transit_hours", "scheduled_port_arrival", "scheduled_departure"),
                      ("actual_transit_hours", "actual_port_arrival", "actual_departure"),
                      ("departure_delay_hours", "actual_departure", "scheduled_departure"),
                      ("port_arrival_delay_hours", "actual_port_arrival", "scheduled_port_arrival")]:
        same(v[col], (v[a]-v[b])/HOUR, "voyage " + col)
    check((v.actual_transit_hours > 0).all(), "positive ocean intervals")
    fleet = v.sort_values("scheduled_departure")
    check(fleet.groupby("route_id").vessel_id.nunique().eq(min(cfg.rounds, cfg.vessels_per_route)).all(),
          "route roster rotation")
    # Empty return/reposition allowance of one nominal crossing plus a day of turnaround.
    ready = fleet.actual_port_arrival + pd.to_timedelta(
        fleet.route_id.map({r.route_id: r.ocean + 24 for r in ROUTES}), unit="h")
    next_start = fleet.groupby("vessel_id").actual_departure.shift(-1)
    check((next_start.isna() | next_start.ge(ready)).all(), "vessel reuse and reposition allowance")
    for frame in [o, t]:
        check(set(frame.shipment_id) == set(s.shipment_id) and len(frame) == len(s)*5 and
              not frame.duplicated(["shipment_id", "stage_order"]).any() and
              frame.stage_order.isin(range(5)).all(), "five unique slots per shipment")
        same(frame.stage_name, frame.stage_order.map(dict(enumerate(STAGES))), "stage order")
    key = ["shipment_id", "stage_order"]
    o = o.sort_values(key).reset_index(drop=True)
    t = t.sort_values(key).reset_index(drop=True)
    ss = s.set_index("shipment_id").loc[t.shipment_id].reset_index()
    vv = v.set_index("voyage_id").loc[ss.voyage_id].reset_index()
    for col in ["actual_timestamp", "scheduled_timestamp"]:
        check(t[col].notna().all() and t.groupby("shipment_id")[col].diff().dropna().gt(pd.Timedelta(0)).all(),
              "ordered physical/scheduled timeline " + col)
        prefix = col.split("_")[0]
        for k, source in [(0, vv[prefix+"_departure"]), (1, vv[prefix+"_port_arrival"]),
                          (4, ss[prefix+"_arrival"])]:
            mask = t.stage_order.eq(k)
            same(t.loc[mask, col], source[mask], "physical endpoint " + col + STAGES[k])
    for col, end, start in [("actual_duration_hours", "actual_arrival", "actual_departure"),
                            ("planned_duration_hours", "scheduled_arrival", "scheduled_departure"),
                            ("final_delay_hours", "actual_arrival", "scheduled_arrival")]:
        same(s[col], (s[end]-s[start])/HOUR, col)
    same(t.stage_delay_hours, (t.actual_timestamp-t.scheduled_timestamp)/HOUR, "physical deviations")
    change = t.groupby("shipment_id").stage_delay_hours.diff()
    same(t.delay_change_hours, change, "signed stage changes")
    same(t.added_delay_hours, change.clip(lower=0), "physical additions")
    same(t.recovered_delay_hours, -change.clip(upper=0), "physical recoveries")
    grouped = t.groupby("shipment_id")
    reconstructed = grouped.stage_delay_hours.first() + grouped.added_delay_hours.sum() - grouped.recovered_delay_hours.sum()
    same(reconstructed, s.set_index("shipment_id").loc[reconstructed.index].final_delay_hours, "delay conservation")
    applicable = t.stage_order.isin([2, 3])
    starts = grouped.actual_timestamp.shift().where(applicable)
    same(t.processing_start_timestamp, starts, "true processing start")
    same(t.processing_hours, (t.actual_timestamp-starts)/HOUR, "true processing interval")
    same(o.scheduled_timestamp, t.scheduled_timestamp, "all planned slots retained")
    reported = ~o.event_missing
    check(reported[o.stage_order.isin([0, 4])].all(), "departure and final always reported")
    same(o.actual_timestamp, t.actual_timestamp.where(reported), "masked physical timestamp")
    same(o.stage_delay_hours, t.stage_delay_hours.where(reported), "masked stage deviation")
    same(o.disruption_type, t.disruption_type.where(reported & ~t.stage_order.isin([1, 2])),
         "tracking reasons exclude unavailable severity classifications")
    check(o.event_available_at.notna().equals(reported) and
          o.loc[reported, "event_available_at"].ge(o.loc[reported, "actual_timestamp"]).all(),
          "release never before occurrence")
    delivered = o.stage_order.eq(4)
    same(o.loc[delivered, "event_available_at"], t.loc[delivered, "actual_timestamp"], "immediate proof of delivery")
    prior_report = o.groupby("shipment_id").event_available_at.shift()
    both = applicable & reported & prior_report.le(o.event_available_at)
    same(o.processing_start_timestamp, starts.where(both), "observed processing start")
    same(o.processing_hours, t.processing_hours.where(both), "observable processing duration")
    shared = o.assign(voyage_id=ss.voyage_id).query("stage_order <= 1")
    for field in ["actual_timestamp", "event_available_at", "event_missing"]:
        check(shared.groupby(["voyage_id","stage_order"])[field].nunique(dropna=False).eq(1).all(),
              "shared maritime report " + field)
    readings = m.set_index("voyage_id").loc[v.voyage_id].reset_index()
    for field, source, clock in [("weather_severity","voyage_weather_severity","weather_available_at"),
                                  ("congestion_level","port_congestion_level","congestion_available_at")]:
        known = readings[field].notna()
        check(known.equals(readings[clock].notna()) and
              readings.loc[known, clock].ge(v.loc[known, "actual_port_arrival"]).all(), "sensor clock " + field)
        same(readings[field], v[source].where(known), "sensor truth " + field)
        check(v[source].between(0,1).all(), "severity in unit interval")
        same(t[field], vv[source].where(t.stage_order.eq(1)), "physical applicability " + field)
        by_voyage = ss.voyage_id.map(m.set_index("voyage_id")[field])
        same(o[field], by_voyage.where(o.stage_order.eq(1) & reported), "observed applicability " + field)
    check(set(p.shipment_id) == set(s.shipment_id) and set(p.split) == {"train","validation","test"},
          "split coverage")
    same(p.voyage_id, p.shipment_id.map(s.set_index("shipment_id").voyage_id), "split foreign keys")
    check(p.groupby("voyage_id").split.nunique().eq(1).all(), "voyage groups intact")
    ordered = v.sort_values("scheduled_departure").voyage_id
    labels = ordered.map(p.drop_duplicates("voyage_id").set_index("voyage_id").split)
    check(labels.map({"train":0, "validation":1, "test":2}).is_monotonic_increasing, "chronological split")
    final_reports = o.loc[o.stage_order.eq(4)].merge(p, on="shipment_id", validate="one_to_one")
    assigned = f.merge(p, on=["shipment_id", "voyage_id"], validate="many_to_one")
    check(len(assigned) == len(f) and assigned.groupby("shipment_id").split.nunique().eq(1).all(),
          "every snapshot inherits its shipment and voyage partition")
    for earlier in [{"train"}, {"train", "validation"}]:
        before = final_reports.split.isin(earlier)
        last_release = final_reports.loc[before, "event_available_at"].max()
        later = v[v.voyage_id.isin(final_reports.loc[~before, "voyage_id"])]
        cutoff = min(later.scheduled_departure.min(), later.actual_departure.min())
        check(last_release < cutoff and last_release < assigned.loc[~assigned.split.isin(earlier),
                                                                   "prediction_timestamp"].min(),
              "earlier final labels strictly available before evaluation")
    check(set(f.shipment_id) == set(s.shipment_id), "snapshot foreign keys")
    policy = split_manifest(s, v, o).set_index("shipment_id").split
    same(p.split, p.shipment_id.map(policy), "closest feasible cumulative shipment cutoffs")
    audit_snapshots(s, v, o, m, f, cfg)
    return ["Keys, schemas and route references", "Shared vessel movements and return allowance",
            "Strictly ordered planned and physical timelines", "Physical interval and signed-delay reconciliation",
            "Observation masks, reporting clocks and sensor applicability", "All snapshot triggers, features and labels",
            "Route roster rotation and disjoint voyage groups",
            "All earlier delivery reports released before each evaluation cutoff"]
