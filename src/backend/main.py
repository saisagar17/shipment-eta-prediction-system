"""Serve frozen ETA models and event-triggered held-out replay."""
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Query as Param
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime

from .schemas import (
    Detail,
    Health,
    Journey,
    Milestone,
    Page,
    PredictionDetail,
    Query,
    Scenario,
    ScenarioQuery,
)
from .service import Replay, RequestError
from .interactions import summarize_interactions
from .schemas import Dashboard, Metadata, Metrics, ModelFeatures


@asynccontextmanager
async def lifespan(app):
    try:
        app.state.repo = Replay()
        app.state.diagnostic = None
    except (OSError, ValueError, KeyError, ImportError) as exc:
        app.state.repo = None
        app.state.diagnostic = (
            f"Artifact startup error: {exc}. Verify submission files and install requirements-tuning.txt."
        )
    yield


app = FastAPI(title="Shipment ETA Prediction System", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(RequestError)
async def request_error(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=exc.status)


def repo():
    if app.state.repo is None:
        raise RequestError(503, app.state.diagnostic)
    return app.state.repo


@app.get("/api/health", response_model=Health)
def health():
    service = app.state.repo
    return dict(
        status="ready" if service else "unavailable",
        regression_loaded=bool(service),
        classification_loaded=False,
        version=service.forecasts.version if service else None,
        diagnostic=app.state.diagnostic,
    )


@app.get("/api/metadata", response_model=Metadata)
def metadata():
    return repo().metadata()


@app.get("/api/dashboard", response_model=Dashboard)
def dashboard(as_of: AwareDatetime | None = None):
    return repo().dashboard(repo().clock(as_of))


@app.get("/api/shipments", response_model=Page)
def shipments(
    search: str = "",
    route: str = "",
    vessel: str = "",
    stage: str = "",
    risk: str = "",
    as_of: AwareDatetime | None = None,
    page: int = Param(1, ge=1),
    size: int = Param(10, ge=1, le=100),
):
    service = repo()
    at = service.clock(as_of)
    rows = []
    for sid in service.plans:
        if search.casefold() not in sid.casefold():
            continue
        row = service.row(sid, at)
        if (
            (route and row["route_id"] != route)
            or (vessel and row["vessel"] != vessel)
            or (stage and row["stage"] != stage)
            or (risk and (row["prediction"] or {}).get("risk") != risk)
        ):
            continue
        rows.append(row)
    rows.sort(key=lambda r: (r["status"] != "In transit", r["shipment_id"]))
    return dict(total=len(rows), page=page, items=rows[(page - 1) * size : page * size])


@app.get("/api/shipments/{sid}", response_model=Detail)
def details(sid: str, as_of: AwareDatetime | None = None, historical: bool = False):
    return repo().detail(sid, repo().clock(as_of), historical)


@app.get("/api/shipments/{sid}/milestones", response_model=list[Milestone])
def milestone_list(sid: str, as_of: AwareDatetime | None = None):
    return repo().detail(sid, repo().clock(as_of), False)["milestones"]


@app.get("/api/shipments/{sid}/propagation", response_model=Journey)
def propagation(sid: str, as_of: AwareDatetime | None = None):
    return repo().propagation(sid, repo().clock(as_of))


@app.post("/api/shipments/{sid}/advance")
def advance(sid: str, as_of: AwareDatetime):
    return repo().advance(sid, repo().clock(as_of))


@app.get("/api/analysis/interactions")
def interactions(as_of: AwareDatetime | None = None):
    service = repo()
    return summarize_interactions(service.plans, service.events, service.sensors, service.clock(as_of))


@app.get("/api/model/comparison")
def comparison(split: Literal["test", "validation"] = "validation"):
    return repo().comparisons[split]


@app.post("/api/predict", response_model=PredictionDetail)
def predict(q: Query):
    return repo().predict(q.shipment_id, repo().clock(q.as_of), q.stage)


@app.post("/api/scenario", response_model=Scenario)
def scenario(q: ScenarioQuery):
    return repo().scenario(
        q.shipment_id, repo().clock(q.as_of), q.stage, q.expected_hours
    )


@app.get("/api/model/metrics", response_model=Metrics)
def metrics(split: Literal["test", "validation"] = "test"):
    return repo().metrics[split]


@app.get("/api/model/features", response_model=ModelFeatures)
def features():
    service = repo()
    return dict(
        definitions=service.definitions,
        importance=service.importance,
        version=service.meta["version"],
    )
