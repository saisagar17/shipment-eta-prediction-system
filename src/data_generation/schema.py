"""Ordered public table contracts and the explicit model input allowlist."""
from .config import STAGES

TRACE = "snapshot_id shipment_id voyage_id prediction_timestamp".split()
FEATURES = """
snapshot_stage completed_stage_count route_id cargo_type final_destination
planned_duration_hours planned_transit_hours remaining_planned_hours elapsed_hours
time_since_last_event_hours departure_day_of_week departure_month departure_delay_hours
port_arrival_delay_hours port_processing_delay_hours customs_delay_hours current_stage_delay_hours
cumulative_added_delay_hours cumulative_recovered_hours observed_weather_severity
observed_congestion_level known_port_processing_hours known_customs_processing_hours
actual_transit_hours_so_far port_arrival_observed port_processing_observed customs_observed
missing_event_count""".split()
TARGETS = "target_final_delay_hours target_actual_arrival target_significant_delay".split()
CATEGORICAL = ["snapshot_stage", "route_id", "cargo_type", "final_destination"]
DELAYS = ["departure_delay_hours", "port_arrival_delay_hours", "port_processing_delay_hours",
          "customs_delay_hours"]
STAGE_DELAYS = dict(zip(STAGES, DELAYS))
VOYAGE = """
voyage_id vessel_id route_id origin_port destination_port scheduled_departure actual_departure
scheduled_port_arrival actual_port_arrival planned_transit_hours actual_transit_hours
departure_delay_hours port_arrival_delay_hours voyage_weather_severity port_congestion_level
voyage_disruption_type""".split()
SHIP = """
shipment_id voyage_id route_id origin destination_port final_destination cargo_type
scheduled_departure actual_departure scheduled_arrival actual_arrival planned_duration_hours
actual_duration_hours final_delay_hours shipment_status""".split()
BASE = "shipment_id stage_order stage_name scheduled_timestamp actual_timestamp".split()
OPS = "processing_start_timestamp processing_hours congestion_level weather_severity stage_delay_hours".split()
OBS = BASE + ["event_available_at"] + OPS + ["event_missing", "disruption_type"]
TRUTH = BASE + OPS + ["disruption_type", "delay_change_hours", "added_delay_hours", "recovered_delay_hours"]
MEAS = "voyage_id weather_severity weather_available_at congestion_level congestion_available_at".split()
TABLES = {"vessel_voyages": VOYAGE, "shipments": SHIP, "ground_truth_milestones": TRUTH,
          "milestones": OBS, "port_call_measurements": MEAS,
          "prediction_snapshots": TRACE + FEATURES + TARGETS,
          "split_manifest": ["shipment_id", "voyage_id", "split"]}
PATHS = {k: f"data/{folder}/{k}.csv" for k, folder in [
    ("vessel_voyages", "raw"), ("shipments", "raw"), ("ground_truth_milestones", "ground_truth"),
    ("milestones", "raw"), ("port_call_measurements", "raw"), ("prediction_snapshots", "processed"),
    ("split_manifest", "processed")]}
DATES = set("""prediction_timestamp scheduled_departure actual_departure scheduled_port_arrival
actual_port_arrival scheduled_arrival actual_arrival scheduled_timestamp actual_timestamp
event_available_at processing_start_timestamp target_actual_arrival weather_available_at
congestion_available_at""".split())
