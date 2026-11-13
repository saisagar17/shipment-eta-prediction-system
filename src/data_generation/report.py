"""Render the validation report directly from the audited CSV values."""
from xml.etree import ElementTree

import pandas as pd

from .config import HOUR, ROOT, ROUTES, STAGES
from .schema import PATHS


def md_table(headers, rows):
    def line(values):
        return "| " + " | ".join(str(x) for x in values) + " |"
    return "\n".join([line(headers), line(["---"] * len(headers)), *(line(row) for row in rows)])


def number(x):
    return f"{x:.2f}"


def quantity(n, total):
    return f"{n}/{total} ({100*n/total:.1f}%)"


def reference_test_result():
    """Read the separately recorded repository QA run, independent of simulation statistics."""
    path = ROOT / "reports/reference_pytest.xml"
    if not path.exists():
        return "The reference-suite run has not been recorded. See the README for the test command."
    suite = ElementTree.parse(path).getroot().find("testsuite")
    total, failed, errors, skipped = (int(suite.get(key)) for key in ("tests", "failures", "errors", "skipped"))
    return (f"The recorded repository reference run collected {total} tests. "
            f"{total-failed-errors-skipped} passed, {failed} failed, {errors} errored and {skipped} skipped. "
            "Counts come from the archived pytest JUnit results for the seed-42 reference cohort.")


def report(cfg, tables, checks):
    v, s, t, o, m, f, p = (tables[k] for k in PATHS)
    delay = s.final_delay_hours
    stages = {k: t[t.stage_order == k].set_index("shipment_id") for k in range(5)}
    ocean_excess = v.actual_transit_hours - v.planned_transit_hours
    weather_r = v.voyage_weather_severity.corr(ocean_excess)
    ship_voy = s.set_index("shipment_id").voyage_id
    handling = stages[2].processing_hours.groupby(ship_voy).mean().reindex(v.voyage_id)
    port_r = handling.corr(v.set_index("voyage_id").port_congestion_level)
    distribution = [("Final delivery", delay)] + [(STAGES[k], stages[k].stage_delay_hours) for k in range(4)]
    dist_table = md_table(["Milestone", "Min", "P25", "Median", "Mean", "P75", "P90", "Max", "SD"],
                          [[name, *map(number,[x.min(), x.quantile(.25),x.median(),x.mean(),x.quantile(.75),
                                               x.quantile(.9),x.max(),x.std()])] for name,x in distribution])
    net = stages[4].stage_delay_hours - stages[0].stage_delay_hours
    late = delay > cfg.significant_delay_hours
    group = t.groupby("shipment_id")
    any_add = group.added_delay_hours.max().gt(0)
    any_rec = group.recovered_delay_hours.max().gt(0)
    previous = group.stage_delay_hours.shift()
    partial_recovery = (t.stage_delay_hours.gt(0) & t.stage_delay_hours.lt(previous)).groupby(t.shipment_id).any()
    amplification = (previous.gt(0) & t.stage_delay_hours.gt(previous)).groupby(t.shipment_id).any()
    bands_final = md_table(["Exclusive delivery band", "Shipments"], [
        [label, quantity(mask.sum(), len(s))] for label, mask in [
            ("More than 2 h early", delay.lt(-2)), ("Within ±2 h, endpoints included", delay.abs().le(2)),
            (f"Moderate (over 2 through {cfg.significant_delay_hours:g} h late)", delay.gt(2) & ~late),
            (f"Significant (over {cfg.significant_delay_hours:g} h late)", late)]])
    outcome = [("Early (signed delay < 0 h)", delay.lt(0)), ("Near schedule (absolute delay ≤ 2 h)", delay.abs().le(2)),
               (f"Significantly delayed (> {cfg.significant_delay_hours:g} h)",late),
               ("At or below significant threshold", ~late),
               ("At least one partial recovery while still late", partial_recovery),
               ("At least one increase in an existing positive delay", amplification),
               ("Net recovery from departure to delivery", net.lt(0)), ("Net amplification from departure to delivery", net.gt(0)),
               ("At least one shorter-than-planned interval",any_rec), ("At least one longer-than-planned interval",any_add)]
    outcome_table = md_table(["Shipment outcome (categories may overlap)", "Shipments"], [
        [label,quantity(mask.sum(),len(s))] for label,mask in outcome])
    route_rows = []
    for route in ROUTES:
        sample = s[s.route_id == route.route_id]
        route_rows.append([route.route_id, f"{route.origin} → {route.port} → {route.destination}",
                           f"{route.ocean*(1-cfg.ocean_variation):.2f}–{route.ocean*(1+cfg.ocean_variation):.2f}",
                           route.weather_scale, v.loc[v.route_id.eq(route.route_id), "vessel_id"].nunique(), len(sample),
                           number(sample.actual_duration_hours.min()),number(sample.actual_duration_hours.median()),
                           number(sample.actual_duration_hours.max()),int(sample.final_delay_hours.le(0).sum()),
                           int(sample.final_delay_hours.gt(cfg.significant_delay_hours).sum())])
    routing = md_table(["Route","Journey","Planned sea range (h)","Weather scale (h)","Vessels","Shipments",
                        "Actual total min (h)","Median (h)","Max (h)","Early/on time","Significant"],route_rows)
    mask_table = md_table(["Unit","Eligible","Missing","Rate"], [
        [label,len(x),int(x.sum()),f"{100*x.mean():.2f}%"] for label,x in [
            ("Intermediate tracking slots",o[o.stage_order.between(1,3)].event_missing),
            ("Shared port-arrival messages",o[o.stage_order==1].assign(voyage_id=lambda a:a.shipment_id.map(ship_voy))
             .drop_duplicates("voyage_id").event_missing),
            ("Port arrival, shipment slots",o[o.stage_order==1].event_missing),
            ("Handling completion messages",o[o.stage_order==2].event_missing),
            ("Customs completion messages",o[o.stage_order==3].event_missing),
            ("Weather sensors, port calls",m.weather_severity.isna()),("Congestion sensors, port calls",m.congestion_level.isna()),
            ("Departure or delivery slots",o[o.stage_order.isin([0,4])].event_missing),
            ("Historical final-delay labels",s.final_delay_hours.isna())]])
    splits = []
    for name in ["train","validation","test"]:
        part = p[p.split==name]
        subset = v[v.voyage_id.isin(part.voyage_id)]
        snaps = f[f.shipment_id.isin(part.shipment_id)]
        significant = int(late[s.shipment_id.isin(part.shipment_id)].sum())
        splits.append([name,len(part),len(subset),len(snaps),subset.scheduled_departure.min().date(),
                       subset.scheduled_departure.max().date(), quantity(significant,len(part)), len(part)-significant])
    split_table = md_table(["Partition","Shipments","Voyages","Snapshots","First booked sailing (UTC)","Last booked sailing (UTC)","Significant","At or below threshold"],splits)
    proof = o[o.stage_order.eq(4)].merge(p, on="shipment_id", validate="one_to_one")
    cut_rows = []
    for label, earlier in [("Validation", ["train"]), ("Test", ["train","validation"])]:
        history = proof.split.isin(earlier)
        last_release = proof.loc[history,"event_available_at"].max()
        future = v[v.voyage_id.isin(proof.loc[~history,"voyage_id"])]
        cutoff = min(future.actual_departure.min(), future.scheduled_departure.min())
        cut_rows.append([label, last_release.isoformat(), cutoff.isoformat(), number((cutoff-last_release)/HOUR)])
    cut_table = md_table(["Evaluation period", "Latest earlier label (UTC)", "Earliest later start (UTC)", "Gap (h)"], cut_rows)
    stage_counts = f.snapshot_stage.value_counts().reindex(STAGES[:4], fill_value=0)
    triggers = md_table(["Triggering report", "Snapshots"], stage_counts.items())
    counts = s.groupby("voyage_id").size().value_counts().sort_index()
    example = s[s.voyage_id==v.iloc[0].voyage_id].iloc[:2]
    example_rows = []
    for k, stage in enumerate(STAGES):
        a,b = [stages[k].loc[sid] for sid in example.shipment_id]
        def stamp(row):
            return row.actual_timestamp.strftime("%Y-%m-%d %H:%M:%S")
        example_rows.append([stage,stamp(a),number(a.stage_delay_hours),stamp(b),number(b.stage_delay_hours)])
    example_table = md_table(["Physical stage",example.iloc[0].shipment_id+" UTC","Deviation (h)",
                              example.iloc[1].shipment_id+" UTC","Deviation (h)"],example_rows)
    example_ops = md_table(["Shipment","Cargo","Handling (h)","Customs (h)","Road (h)","Final delay (h)"],
                           [[r.shipment_id,r.cargo_type,number(stages[2].loc[r.shipment_id,"processing_hours"]),
                             number(stages[3].loc[r.shipment_id,"processing_hours"]),
                             number((r.actual_arrival-stages[3].loc[r.shipment_id,"actual_timestamp"])/HOUR),
                             number(r.final_delay_hours)] for r in example.itertuples()])
    fleet = v.sort_values("scheduled_departure")
    idle = (fleet.groupby("vessel_id").actual_departure.shift(-1) - fleet.actual_port_arrival).dropna()/HOUR
    closure = stages[0].stage_delay_hours + group.added_delay_hours.sum() - group.recovered_delay_hours.sum()
    err = (closure - stages[4].stage_delay_hours).abs().max()
    sizes = md_table(["Table","Rows"],[[key,len(tables[key])] for key in PATHS])
    sensor_effects = []
    for label,index,response in [("Weather / excess sailing",v.voyage_weather_severity,ocean_excess),
                                 ("Congestion / mean handling",v.port_congestion_level,handling.to_numpy())]:
        pairs = pd.DataFrame({"severity":index.to_numpy(),"hours":response})
        pairs = pairs.sort_values("severity")
        n = max(1,len(pairs)//4)
        sensor_effects.append([label, n,number(pairs.head(n).hours.mean()),number(pairs.tail(n).hours.mean())])
    bands = md_table(["Driver / outcome","Calls per tail","Lowest severity mean (h)","Highest severity mean (h)"],sensor_effects)
    return f"""# Shipment ETA synthetic dataset validation

## Scope and design

This completed-history cohort supports supervised prediction of inland delivery time and signed delay at successive tracking reports. All timings, operating rules and probabilities are scenario assumptions. Seed {cfg.seed} drives separate schedule, voyage, cargo and observation streams. The scheduler builds every planned timestamp before drawing realized disruptions. UTC clocks are rounded to the nearest second.

{sizes}

The fleet has {v.vessel_id.nunique()} vessels. Each route rotates a roster of {cfg.vessels_per_route} ships in waves spaced {cfg.cycle_days} days apart. Randomized sailing order within a wave gives one voyage per day for five days. The scheduler assigns the vessel before drawing departure reliability, weather and congestion for the port call. All cargo on that voyage shares its sailing clocks and call conditions. Unrecorded empty return and turnaround use an allowance of one nominal ocean duration plus 24 hours before reuse. Minimum observed idle interval across {len(idle)} vessel reuses is {idle.min():.2f} hours. The voyage-size distribution is {", ".join(f"{n} voyages with {size} shipments" for size,n in counts.items())}.

## Routes and schedule assumptions

{routing}

Ocean allowances vary uniformly within the stated range. Handling, customs and road baselines vary ±10% around route-specific values. Cargo handling and documentation increments enter the first two baselines before booking. Planned allowances then include {cfg.port_buffer:g} h of handling slack, {cfg.customs_buffer:g} h of customs slack and {cfg.inland_buffer:g} h of road slack. Route baselines and cargo increments are recorded in `dataset_config.json`.

## Physical stages and delay mechanisms

The earlier design allowed 8.5 h of downstream slack on every booking. This version allows {cfg.port_buffer + cfg.customs_buffer + cfg.inland_buffer:g} h across three stages. Handling retains the largest buffer because it includes queues and unloading. Customs and road retain smaller allowances for routine variability. Inspections and missed windows can exceed those allowances. Changes enter the booked schedule before sailing and can affect later dispatch decisions. The same scenario probabilities govern every vessel.

1. Vessel departure uses routine, moderate and severe cases with probabilities {", ".join(f"{x:.0%}" for x in cfg.departure_probabilities)}. Uniform deviations span −1 to +2, +2 to +8 and +8 to +18 hours respectively.
2. Ocean duration adds route scale × weather severity^1.5 and normal sailing variation (mean −1.8 h, SD 1.8 h) to the booking. Severity follows Beta(1.5, 2). Every consignment on the voyage shares this realization.
3. Port handling includes waiting and unloading. Route and cargo effort are increased by {cfg.congestion_linear:g}c + {cfg.congestion_quadratic:g}c² hours for shared congestion c ~ Beta(1.7, 1.9), plus normal variation (mean −0.8 h, SD 1.3 h).
4. Customs adds gamma-distributed documentation effort, uniform workload variation and normal noise to route and cargo effort. An independent inspection with probability {cfg.inspection_probability:.0%} adds 4–14 hours. There were {int((stages[3].disruption_type=="inspection").sum())} inspections.
5. Inland duration uses the booked destination-specific road baseline before slack, plus traffic noise. Late releases can shorten dispatch by 20% of lateness up to the road buffer. Releases over 3 h late miss their next window with probability 30%, compared with 6% otherwise. A missed window adds 3–10 h. Each realized interval has a 1 h physical floor.

Signed deviation at a stage equals actual time minus booked time. Over each physical interval the change equals actual duration minus planned duration. Positive changes add delay and negative changes recover it. The initial deviation plus subsequent additions minus recoveries reconstructs final delay. The maximum absolute reconciliation residual after CSV serialization was {err:.2e} h.

## Distribution checks

{dist_table}

All values above are signed schedule deviations in hours. SD is the sample standard deviation. Outcomes below count shipments once.

{bands_final}

{outcome_table}

The voyage simulator drew {v.voyage_disruption_type.eq("severe_departure").sum()} severe departure disruptions (8–18 h). Propagation frequencies above use the complete physical ledger, including stages absent from tracking.

Across {len(v)} port calls, the Pearson correlation between weather and sailing time above the route-specific booking was {weather_r:.3f}. The correlation between congestion and mean cargo handling duration per call was {port_r:.3f}. Each voyage contributes one observation to each calculation.

{bands}

## Observation masks and feature availability

Sample missing reports and sensors uniformly without replacement in their eligible populations. Round requested numbers to the nearest whole report (half up). Port-arrival reports, their release times and both sensor messages are shared at voyage level. Handling and customs reports have shipment-specific masks. The weather and congestion sensors have independent masks and release clocks 5–60 minutes after physical port arrival. Their measurements may arrive even when the tracking message is missing.

{mask_table}

{triggers}

Each observed milestone summary can mirror a sensor value on a reported arrival row. Use the matching sensor release clock from `port_call_measurements.csv` for as-of reads. Tracking lag is 0–{cfg.max_event_lag_minutes} minutes, with immediate final delivery confirmation. A missing tracking event retains its booked slot and loses its occurrence time, report time, reason and deviation. Processing begins at the previous boundary and its interval is available only when both boundary reports exist. Fields outside their applicable stages are blank.

Snapshots use a planning projection, time-filtered event messages and independent sensor releases. At departure, future events and unreleased sensors stay blank. The count of missing events includes only gaps preceding the highest observed stage. Pending and permanently missing reports are indistinguishable at that cutoff. The archived flag `event_missing` is retrospective. Across a tracking gap, cumulative changes capture only the visible net difference. At a report trigger, event age is time since physical occurrence, so it can equal the report lag. Labels are attached after feature construction from completed shipment records. A later status service can reconstruct live progress from the latest available report.

## Shared voyage example

Voyage {v.iloc[0].voyage_id} on vessel {v.iloc[0].vessel_id} carried the two consignments below. The example uses the physical ledger, including any event absent from tracking.

{example_table}

{example_ops}

## Partitions and integrity checks

Sort voyages by scheduled departure and voyage ID. For each possible cut, compare the latest final-delivery report of **all** earlier consignments with the earliest scheduled or physical departure among **all** later voyages. A cut is eligible only if the report strictly precedes that departure. Among eligible pairs, minimize the sum of absolute distances from the cumulative 70% and 85% shipment targets. Equal costs select the earlier pair in voyage order. All voyages are retained. No delay magnitude, class label or route outcome statistic participates in selecting a boundary.

{split_table}

{cut_table}

The on-disk audit passed the following checks for this run.

""" + "\n".join("- "+x for x in checks) + """

The audit independently reconstructs each as-of feature from persisted tracking and sensor clocks. Tests move individual release times, alter future outcomes across a route, exercise early evaluation departures, and compare generated file bytes.

## Recorded automated test results

""" + reference_test_result() + """

## Limits of interpretation

The synthetic durations, thresholds, distributions and masks lack carrier calibration. Routes have dedicated vessel pools, and cargo on a shared voyage experiences correlated maritime conditions. The partition table shows the small numbers of independent voyage groups and significantly late consignments available for evaluation. Multiple snapshots from a single late shipment carry the same label. The simulation omits seasonal and inter-port dependencies, detailed repositioning, resource queues and correlated outages.
"""
