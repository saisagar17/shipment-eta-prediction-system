from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Risk = Literal["Low", "Moderate", "High"]


class Query(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shipment_id: str
    as_of: AwareDatetime | None = None
    stage: str | None = None


class ScenarioQuery(Query):
    expected_hours: float = Field(gt=0, le=500, allow_inf_nan=False)


class Prediction(BaseModel):
    shipment_id: str
    observation_timestamp: datetime
    stage: str
    scheduled_eta: datetime
    predicted_eta: datetime
    delay: float
    risk: Risk
    version: str


class Factor(BaseModel):
    feature: str
    hours: float


class ModelFactor(Factor):
    available: bool


class GlobalWeight(BaseModel):
    feature: str
    value: float


class Comparison(BaseModel):
    name: str
    delay: float
    predicted_eta: datetime
    base_hours: float
    anchor_hours: float | None
    contributions: list[ModelFactor]
    global_importance: list[GlobalWeight]
    global_method: str
    local_method: str


class PredictionDetail(Prediction):
    reported_conditions: dict[str, str]
    comparisons: dict[str, Comparison]
    base_hours: float
    contributions: list[Factor]
    observed: dict[str, float | None]
    summary: str


class Row(BaseModel):
    attention_reasons: list[str]
    shipment_id: str
    voyage_id: str
    route_id: str
    route: str
    vessel: str
    cargo: str
    scheduled_eta: datetime
    stage: str
    status: str
    prediction: Prediction | None


class Page(BaseModel):
    total: int
    page: int
    items: list[Row]


class Milestone(BaseModel):
    stage: str
    order: int
    scheduled: datetime
    actual: datetime | None
    released: datetime | None
    state: str
    deviation: float | None
    change: float | None
    across_gap: bool
    added: float | None
    recovered: float | None


class Update(Prediction):
    change_from_previous: float | None


class Journey(BaseModel):
    milestones: list[Milestone]
    updates: list[Update]


class Detail(Row):
    as_of: datetime
    historical: bool
    actual_delivery: datetime | None
    milestones: list[Milestone]


class Scenario(BaseModel):
    hypothetical: bool
    stage: str
    baseline_hours: float
    expected_hours: float
    baseline: Prediction
    scenario: Prediction
    change_delay: float
    change_eta_hours: float


class Health(BaseModel):
    status: str
    regression_loaded: bool
    classification_loaded: bool
    version: str | None
    diagnostic: str | None


class RouteInfo(BaseModel):
    route_id: str
    origin: str
    destination_port: str
    final_destination: str


class Demonstration(BaseModel):
    id: str
    type: str
    as_of: AwareDatetime


class Metadata(BaseModel):
    demonstrations: list[Demonstration]
    routes: list[RouteInfo]
    cargo: list[str]
    vessels: list[str]
    stages: list[str]
    start: datetime
    end: datetime
    default_time: datetime
    version: str
    modes: list[str]
    cohort: str
    shipments: list[str]


class Daily(BaseModel):
    date: str
    predicted: float
    observed: float
    n: int


class Dashboard(BaseModel):
    total: int
    active: int
    delivered: int
    average: float | None
    risks: dict[str, int]
    stages: dict[str, int]
    trend: list[Daily]
    on_time: float | None
    attention: list[Row]


class Score(BaseModel):
    n: int
    shipments: int
    voyages: int
    mae: float
    rmse: float
    median: float
    p90: float
    r2: float | None


class Group(Score):
    name: str
    category: str


class Point(BaseModel):
    snapshot_id: str
    shipment_id: str
    voyage_id: str
    snapshot_stage: str
    target_final_delay_hours: float
    predicted: float


class Metrics(BaseModel):
    comparison: dict[str, Score]
    subgroups: list[Group]
    points: list[Point]


class Definition(BaseModel):
    column: str
    business_meaning: str
    unit: str


class Importance(BaseModel):
    feature: str
    increase_mae: float
    sd: float


class ModelFeatures(BaseModel):
    importance: list[Importance]
    definitions: list[Definition]
    version: str
