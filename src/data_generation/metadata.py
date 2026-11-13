"""Column-level contracts shared by the dictionary export and on-disk audit."""
import pandas as pd

from .schema import CATEGORICAL, DATES, DELAYS, FEATURES, OPS, TABLES, TARGETS, TRACE

MEANINGS = {
    "voyage_id": "Identifier for one scheduled maritime journey and its cargo group.",
    "vessel_id": "Physical ship drawn from the route's rotating roster and reused across sailing cycles.",
    "shipment_id": "Identifier for one cargo consignment.",
    "snapshot_id": "Trace key combining shipment and triggering milestone order.",
    "route_id": "Planned port-to-inland route definition.",
    "origin_port": "Maritime departure port.", "origin": "Maritime departure port.",
    "destination_port": "Port where the vessel arrives and cargo is unloaded.",
    "final_destination": "Inland destination where final delivery occurs.",
    "cargo_type": "Booked cargo category used for handling and customs allowances.",
    "scheduled_departure": "Planned vessel departure, shared by all cargo on the voyage.",
    "actual_departure": "Physical vessel departure, shared by all cargo on the voyage.",
    "scheduled_port_arrival": "Planned departure plus planned ocean transit.",
    "actual_port_arrival": "Physical departure plus realized ocean transit.",
    "scheduled_arrival": "End of the booked inland delivery allowance.",
    "actual_arrival": "Physical final delivery to the inland destination.",
    "planned_transit_hours": "Scheduled port arrival minus scheduled vessel departure.",
    "actual_transit_hours": "Physical port arrival minus physical vessel departure.",
    "departure_delay_hours": "Signed actual minus planned vessel departure.",
    "port_arrival_delay_hours": "Signed actual minus planned destination-port arrival.",
    "port_processing_delay_hours": "Signed schedule deviation at handling completion.",
    "customs_delay_hours": "Signed schedule deviation at customs completion.",
    "voyage_weather_severity": "Realized ocean weather severity shared by the voyage.",
    "port_congestion_level": "Realized destination port-call congestion shared by the voyage.",
    "voyage_disruption_type": "Sampled vessel departure scenario.",
    "planned_duration_hours": "Scheduled final delivery minus scheduled departure.",
    "actual_duration_hours": "Actual final delivery minus actual departure.",
    "final_delay_hours": "Signed actual minus scheduled final delivery.",
    "shipment_status": "Historical outcome, completed for every consignment.",
    "stage_order": "Ordinal stage position, from 0 at departure to 4 at delivery.",
    "stage_name": "Booked milestone name at the given position.",
    "scheduled_timestamp": "Booked UTC timestamp of this stage.",
    "actual_timestamp": "Physical occurrence time of the milestone.",
    "event_available_at": "Time the tracking report containing the event first became available.",
    "processing_start_timestamp": "Previous boundary of port or customs processing, including queue time.",
    "processing_hours": "Elapsed port or customs interval between consecutive boundaries, including queues.",
    "congestion_level": "Port-call congestion index. In milestone tables it applies at port arrival.",
    "weather_severity": "Realized ocean weather index. In milestone tables it applies at port arrival.",
    "stage_delay_hours": "Signed actual minus scheduled timestamp of this stage.",
    "event_missing": "Historical flag for a permanently absent tracking message.",
    "disruption_type": "Realized stage scenario or routine; port and weather tags use severity thresholds.",
    "delay_change_hours": "Current schedule deviation less preceding physical stage deviation.",
    "added_delay_hours": "Positive part of the signed interval change.",
    "recovered_delay_hours": "Magnitude of the negative part of the signed interval change.",
    "weather_available_at": "Release time for the port-call ocean weather summary.",
    "congestion_available_at": "Release time for the port-call congestion measurement.",
    "prediction_timestamp": "As-of cutoff when a qualifying milestone report arrived.",
    "snapshot_stage": "Highest reported stage at the cutoff.",
    "completed_stage_count": "Number of distinct reported stages at the cutoff.",
    "remaining_planned_hours": "Scheduled final delivery minus prediction cutoff; may be negative.",
    "elapsed_hours": "Prediction cutoff minus reported physical departure.",
    "time_since_last_event_hours": "Cutoff minus physical occurrence of most advanced reported event.",
    "departure_day_of_week": "UTC scheduled departure weekday with Monday equal to zero.",
    "departure_month": "UTC scheduled departure calendar month, January equal to one.",
    "current_stage_delay_hours": "Signed deviation at most advanced reported stage.",
    "cumulative_added_delay_hours": "Sum of positive changes between visible deviations, excluding initial deviation.",
    "cumulative_recovered_hours": "Sum of negative change magnitudes between visible deviations, excluding initial deviation.",
    "observed_weather_severity": "Latest released voyage weather index.",
    "observed_congestion_level": "Latest released port-call congestion index.",
    "known_port_processing_hours": "Reported handling completion minus reported port arrival, including queue time.",
    "known_customs_processing_hours": "Reported customs completion minus reported handling completion.",
    "actual_transit_hours_so_far": "Completed sailing interval when both maritime boundary reports are available.",
    "port_arrival_observed": "Port arrival report was available at cutoff.",
    "port_processing_observed": "Handling completion report was available at cutoff.",
    "customs_observed": "Customs completion report was available at cutoff.",
    "missing_event_count": "Earlier planned slots without reports below the most advanced reported stage.",
    "target_final_delay_hours": "Historical signed final delivery deviation, repeated across a shipment's snapshots.",
    "target_actual_arrival": "Historical inland delivery timestamp, repeated across a shipment's snapshots.",
    "target_significant_delay": "One when final deviation strictly exceeds the configured threshold, else zero.",
    "split": "Chronological voyage partition inherited by every snapshot, with earlier labels released before evaluation.",
}

PLANNED = set("""voyage_id vessel_id shipment_id route_id origin origin_port destination_port final_destination
cargo_type scheduled_departure scheduled_arrival scheduled_port_arrival scheduled_timestamp stage_order stage_name
planned_transit_hours planned_duration_hours departure_day_of_week departure_month""".split())
NULLABLE = {
    "milestones": {"actual_timestamp", "event_available_at", *OPS, "disruption_type"},
    "ground_truth_milestones": {*OPS[:4], "delay_change_hours", "added_delay_hours", "recovered_delay_hours"},
    "port_call_measurements": set(TABLES["port_call_measurements"][1:]),
    "prediction_snapshots": {*DELAYS[1:], "observed_weather_severity", "observed_congestion_level",
                             "known_port_processing_hours", "known_customs_processing_hours", "actual_transit_hours_so_far"},
}
SOURCES = {"vessel_voyages": "Voyage schedule and shared sailing simulator",
           "shipments": "Booking plan and physical consignment simulator",
           "ground_truth_milestones": "Physical event ledger before observation masking",
           "milestones": "Tracking feed after shared and shipment-specific report masking",
           "port_call_measurements": "Independent weather and port-call sensor feeds",
           "prediction_snapshots": "As-of replay of plans, reported events and released sensors",
           "split_manifest": "Closest cumulative 70% and 85% cuts among label-complete voyage boundaries"}


def dtype_unit(col):
    if col in DATES:
        return "datetime", "UTC, seconds"
    if col.endswith("_hours") or col == "actual_transit_hours_so_far":
        return "float", "hours"
    if "severity" in col or "congestion_level" in col:
        return "float", "index 0–1"
    if col == "event_missing" or col.endswith("_observed"):
        return "boolean", "flag"
    if col in ("departure_month", "departure_day_of_week", "stage_order", "target_significant_delay") or col.endswith("_count"):
        return "integer", "binary" if col.startswith("target_") else "integer"
    return "string", "category" if not col.endswith("_id") else "identifier"


def availability(table, col):
    if col in PLANNED:
        return "Booking or voyage plan"
    if col in TARGETS or col in {"actual_arrival","final_delay_hours","actual_duration_hours","shipment_status"}:
        return "Final delivery / historical labels"
    if col in {"event_missing","split"}:
        return "Retrospective dataset preparation"
    if table == "ground_truth_milestones":
        return "Physical event ledger only"
    if col in {"weather_severity","congestion_level","weather_available_at","congestion_available_at",
               "observed_weather_severity","observed_congestion_level","voyage_weather_severity","port_congestion_level"}:
        return "Independent port-call sensor release after physical arrival"
    if table == "prediction_snapshots":
        if col in DELAYS:
            return ["Departure report", "Port arrival report", "Handling completion report", "Customs report"][DELAYS.index(col)]
        if col in {"known_port_processing_hours","known_customs_processing_hours","actual_transit_hours_so_far"}:
            return "Both adjacent boundary reports available"
        return "As of the triggering report"
    if col in {"actual_departure","departure_delay_hours","voyage_disruption_type"}:
        return "Departure report"
    if col in {"actual_port_arrival","port_arrival_delay_hours","actual_transit_hours"}:
        return "Port arrival report (plus departure for elapsed transit)"
    return "Applicable stage report; duration requires both boundary reports"


def data_dictionary():
    rows = []
    for table, cols in TABLES.items():
        for col in cols:
            dtype, unit = dtype_unit(col)
            hidden = table in {"vessel_voyages","shipments","ground_truth_milestones"} and col not in PLANNED
            source = SOURCES[table]
            if col in TARGETS:
                source = "Historical shipment outcomes joined after feature calculation"
            rows.append(dict(dataset=table+".csv", column=col, data_type=dtype, business_meaning=MEANINGS[col],
                             unit=unit, nullable=col in NULLABLE.get(table, set()), source=source,
                             known_before_departure=col in PLANNED, observable_at=availability(table,col),
                             hidden_ground_truth=hidden, eligible_ml_input=table=="prediction_snapshots" and col in FEATURES,
                             is_target=col in TARGETS))
    return pd.DataFrame(rows)


def feature_schema():
    return dict(approved_input_columns=FEATURES, categorical_inputs=CATEGORICAL,
                trace_columns=TRACE, target_columns=TARGETS, null_encoding="empty CSV field",
                categorical_encoding="Choose and fit encoders only on the training partition.",
                split_join_key="shipment_id", split_group="voyage_id",
                split_cutoff="All earlier final-delivery reports must precede every later scheduled and actual sailing.",
                event_time_zone="UTC")
