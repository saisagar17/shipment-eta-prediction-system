"""Public design parameters. All intervals are hours unless otherwise specified."""
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
STAGES = ("origin_departure", "port_arrival", "port_processing_complete",
          "customs_clearance_complete", "final_delivery")
HOUR = pd.Timedelta(hours=1)


@dataclass(frozen=True)
class Route:
    route_id: str
    origin: str
    port: str
    destination: str
    ocean: int
    port_base: float
    customs_base: float
    inland_base: float
    weather_scale: float


ROUTES = (
    Route("R01", "Chennai", "Mumbai", "Pune", 72, 6, 3, 5, 6),
    Route("R02", "Singapore", "Chennai", "Bengaluru", 120, 7, 4, 8, 9),
    Route("R03", "Kochi", "Mumbai", "Nashik", 48, 6, 3, 6, 5),
    Route("R04", "Dubai", "Mumbai", "Pune", 168, 8, 5, 5, 12),
    Route("R05", "Colombo", "Chennai", "Hyderabad", 48, 7, 4, 13, 4),
)
# Additional handling / document effort in hours.
CARGO = {"general_goods": (0, 0), "electronics": (1, 1.5),
         "automotive_parts": (1.5, 0.5), "industrial_equipment": (3, 2)}


@dataclass(frozen=True)
class Config:
    seed: int = 42
    start_utc: str = "2025-01-06T06:00:00Z"
    rounds: int = 10
    cycle_days: int = 22
    ocean_variation: float = 0.07
    departure_probabilities: tuple = (0.70, 0.20, 0.10)
    vessels_per_route: int = 2
    port_buffer: float = 2.0
    customs_buffer: float = 1.5
    inland_buffer: float = 1.5
    congestion_linear: float = 2.0
    congestion_quadratic: float = 9.0
    inspection_probability: float = 0.14
    missing_event_rate: float = 0.10
    missing_weather_rate: float = 0.05
    missing_congestion_rate: float = 0.10
    max_event_lag_minutes: int = 20
    significant_delay_hours: float = 6.0

    def metadata(self):
        return {**asdict(self), "routes": [asdict(r) for r in ROUTES],
                "cargo_extra_hours_port_customs": CARGO, "stages": STAGES,
                "time_zone": "UTC", "time_resolution": "1 second",
                "train_validation_test_fractions": [0.70, 0.15, 0.15]}
