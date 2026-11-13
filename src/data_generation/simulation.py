"""Schedule first, realize shared maritime events, then realize cargo-specific intervals."""
import numpy as np
import pandas as pd

from .config import CARGO, HOUR, ROUTES, STAGES, Config
from .schema import SHIP, TRUTH, VOYAGE


def interval(hours):
    """Round a duration once at the physical clock boundary."""
    return pd.Timedelta(seconds=round(3600 * hours))


def plan_voyages(cfg, rng):
    voyages = []
    for wave in range(cfg.rounds):
        for slot, index in enumerate(rng.permutation(len(ROUTES))):
            route = ROUTES[index]
            start = pd.Timestamp(cfg.start_utc) + pd.Timedelta(days=wave * cfg.cycle_days + slot)
            ocean = interval(route.ocean * rng.uniform(1 - cfg.ocean_variation, 1 + cfg.ocean_variation))
            # Rotate a route's roster before drawing any realized voyage conditions.
            vessel_number = index + 1 + len(ROUTES) * (wave % cfg.vessels_per_route)
            voyages.append(dict(voyage_id=f"VG{len(voyages)+1:03}", vessel_id=f"V{vessel_number:02}",
                                route_id=route.route_id, origin_port=route.origin,
                                destination_port=route.port, scheduled_departure=start,
                                scheduled_port_arrival=start + ocean, planned_transit_hours=ocean / HOUR))
    return voyages


def realize_voyage(plan, cfg, route, rng):
    scenario = rng.choice(["routine", "moderate_departure", "severe_departure"],
                          p=cfg.departure_probabilities)
    limits = {"routine": (-1, 2), "moderate_departure": (2, 8), "severe_departure": (8, 18)}
    departure = plan["scheduled_departure"] + interval(rng.uniform(*limits[scenario]))
    weather = rng.beta(1.5, 2)
    congestion = rng.beta(1.7, 1.9)
    ocean = max(1, plan["planned_transit_hours"] + route.weather_scale * weather**1.5
                + rng.normal(-1.8, 1.8))
    arrival = departure + interval(ocean)
    return dict(**plan, actual_departure=departure, actual_port_arrival=arrival,
                actual_transit_hours=(arrival - departure) / HOUR,
                departure_delay_hours=(departure - plan["scheduled_departure"]) / HOUR,
                port_arrival_delay_hours=(arrival - plan["scheduled_port_arrival"]) / HOUR,
                voyage_weather_severity=weather, port_congestion_level=congestion,
                voyage_disruption_type=scenario)


def plan_consignments(voyages, cfg, rng):
    """One set of 4, 4, 5, 6, 6 consignments in random voyage order per wave."""
    plans = []
    routes = {r.route_id: r for r in ROUTES}
    for offset in range(0, len(voyages), 5):
        sizes = rng.permutation([4, 4, 5, 6, 6])
        for voyage, size in zip(voyages[offset:offset+5], sizes):
            route = routes[voyage["route_id"]]
            for _ in range(size):
                cargo = rng.choice(list(CARGO))
                handling, documents = CARGO[cargo]
                durations = [
                    (route.port_base + handling) * rng.uniform(.9, 1.1) + cfg.port_buffer,
                    (route.customs_base + documents) * rng.uniform(.9, 1.1) + cfg.customs_buffer,
                    route.inland_base * rng.uniform(.9, 1.1) + cfg.inland_buffer,
                ]
                timeline = [voyage["scheduled_departure"], voyage["scheduled_port_arrival"]]
                for duration in durations:
                    timeline.append(timeline[-1] + interval(duration))
                plans.append(dict(shipment_id=f"SHP{len(plans)+1:04}", voyage_id=voyage["voyage_id"],
                                  cargo_type=cargo, route=route, timeline=timeline))
    return plans


def realize_cargo(plan, voyage, cfg, rng):
    """Return physical timestamps and stage labels. Durations include queue time."""
    route = plan["route"]
    handling, documents = CARGO[plan["cargo_type"]]
    congestion = voyage["port_congestion_level"]
    port_hours = max(1, route.port_base + handling + cfg.congestion_linear * congestion
                     + cfg.congestion_quadratic * congestion**2 + rng.normal(-.8, 1.3))
    inspected = rng.random() < cfg.inspection_probability
    paperwork = rng.gamma(1.5, .65)
    workload = rng.uniform(-1.4, 1.4)
    customs_hours = max(1, route.customs_base + documents + paperwork + workload
                        + (rng.uniform(4, 14) if inspected else 0) + rng.normal(-.6, .7))
    actual = [voyage["actual_departure"], voyage["actual_port_arrival"]]
    actual.append(actual[-1] + interval(port_hours))
    actual.append(actual[-1] + interval(customs_hours))
    timeline = plan["timeline"]
    late_release = (actual[-1] - timeline[3]) / HOUR
    missed = rng.random() < (0.30 if late_release > 3 else 0.06)
    # A late release can use expedited road dispatch. Window waits are separate.
    dispatch_saving = min(max(0, late_release) * .20, cfg.inland_buffer)
    road_base = (timeline[4] - timeline[3]) / HOUR - cfg.inland_buffer
    inland_hours = max(1, road_base + rng.normal(.8, 1.5) - dispatch_saving
                       + (rng.uniform(3, 10) if missed else 0))
    actual.append(actual[-1] + interval(inland_hours))
    labels = [voyage["voyage_disruption_type"],
              "rough_weather" if voyage["voyage_weather_severity"] >= .7 else "routine",
              "congested_port" if congestion >= .65 else "routine",
              "inspection" if inspected else "routine", "missed_window" if missed else "routine"]
    return actual, labels


def physical_records(cfg: Config, schedule_rng, voyage_rng, cargo_rng):
    routes = {r.route_id: r for r in ROUTES}
    voyage_plans = plan_voyages(cfg, schedule_rng)
    consignment_plans = plan_consignments(voyage_plans, cfg, schedule_rng)
    voyages = {p["voyage_id"]: realize_voyage(p, cfg, routes[p["route_id"]], voyage_rng)
               for p in voyage_plans}
    shipments, truth = [], []
    for p in consignment_plans:
        v = voyages[p["voyage_id"]]
        route = p["route"]
        scheduled = p["timeline"]
        actual, labels = realize_cargo(p, v, cfg, cargo_rng)
        delays = [(a - s) / HOUR for a, s in zip(actual, scheduled)]
        shipments.append(dict(shipment_id=p["shipment_id"], voyage_id=p["voyage_id"],
                              route_id=route.route_id, origin=route.origin, destination_port=route.port,
                              final_destination=route.destination, cargo_type=p["cargo_type"],
                              scheduled_departure=scheduled[0], actual_departure=actual[0],
                              scheduled_arrival=scheduled[4], actual_arrival=actual[4],
                              planned_duration_hours=(scheduled[4]-scheduled[0])/HOUR,
                              actual_duration_hours=(actual[4]-actual[0])/HOUR,
                              final_delay_hours=delays[4], shipment_status="completed"))
        for k, stage in enumerate(STAGES):
            change = delays[k] - delays[k-1] if k else np.nan
            truth.append(dict(shipment_id=p["shipment_id"], stage_order=k, stage_name=stage,
                              scheduled_timestamp=scheduled[k], actual_timestamp=actual[k],
                              processing_start_timestamp=actual[k-1] if k in (2, 3) else pd.NaT,
                              processing_hours=(actual[k]-actual[k-1])/HOUR if k in (2, 3) else np.nan,
                              congestion_level=v["port_congestion_level"] if k == 1 else np.nan,
                              weather_severity=v["voyage_weather_severity"] if k == 1 else np.nan,
                              stage_delay_hours=delays[k], disruption_type=labels[k],
                              delay_change_hours=change, added_delay_hours=max(change, 0),
                              recovered_delay_hours=max(-change, 0)))
    return (pd.DataFrame(voyages.values(), columns=VOYAGE), pd.DataFrame(shipments, columns=SHIP),
            pd.DataFrame(truth, columns=TRUTH))
