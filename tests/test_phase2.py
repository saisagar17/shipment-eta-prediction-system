import json
import joblib
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from data_generation.config import ROOT, HOUR
from data_generation.schema import FEATURES, TRACE, TARGETS
from ml.model import eta, explain, pipeline
from ml.train import baselines, scores


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_metadata_and_evaluations(client):
    assert client.get("/api/health").json()["regression_loaded"]
    assert client.get("/api/metadata").json()["cohort"] == "Held-out test voyages"
    for split in ["validation", "test"]:
        data = client.get("/api/model/metrics", params={"split": split}).json()
        actual = np.array([p["target_final_delay_hours"] for p in data["points"]])
        predicted = np.array([p["predicted"] for p in data["points"]])
        assert data["comparison"]["Random Forest"]["mae"] == pytest.approx(
            abs(actual - predicted).mean()
        )
    assert len(client.get("/api/model/features").json()["definitions"]) == len(FEATURES)


def test_reloaded_prediction_matches_all_evaluation_rows(client):
    service = app.state.repo
    for p in service.metrics["test"]["points"]:
        stage = p["snapshot_stage"]
        event = service.select(p["shipment_id"], service.end, stage)
        pred = service.cached(
            p["shipment_id"], event.event_available_at, service.meta["version"]
        )
        assert pred["delay"] == pytest.approx(p["predicted"])
        assert pred["predicted_eta"] == eta(pred["scheduled_eta"], pred["delay"])


def test_fit_save_reload_and_unknown_category(tmp_path):
    schema = json.loads((ROOT / "data/metadata/feature_schema.json").read_text())
    snapshots = pd.read_csv(ROOT / "data/processed/prediction_snapshots.csv")
    manifest = pd.read_csv(ROOT / "data/processed/split_manifest.csv")
    train = snapshots.merge(
        manifest.query("split=='train'"), on=["shipment_id", "voyage_id"]
    )
    model = (
        pipeline(schema)
        .set_params(forest__n_estimators=3)
        .fit(train[FEATURES], train.target_final_delay_hours)
    )
    joblib.dump(model, tmp_path / "small.joblib")
    model = joblib.load(tmp_path / "small.joblib")
    assert not set(model.feature_names_in_) & set(TRACE + TARGETS)
    frame = train.iloc[:1][FEATURES].copy()
    frame["route_id"] = "unknown"
    frame["observed_weather_severity"] = np.nan
    y = model.predict(frame)
    why = explain(model, frame)
    assert y.shape == (1,) and np.isfinite(y[0])
    assert y[0] == pytest.approx(
        why["base_hours"] + sum(r["hours"] for r in why["contributions"])
    )


def test_baselines_weight_unique_shipments():
    train = pd.DataFrame(
        {
            "shipment_id": ["a", "a", "b"],
            "route_id": ["R", "R", "R"],
            "target_final_delay_hours": [2, 2, 8],
        }
    )
    query = pd.DataFrame(
        {"route_id": ["R", "new"], "current_stage_delay_hours": [-1, np.nan]}
    )
    p = baselines(train, query)
    assert list(p["Route median"]) == [5, 5]
    assert list(p["Current delay"]) == [-1, 0]
    assert list(p["Scheduled ETA"]) == [0, 0]


def test_search_filters_clock_and_history(client):
    service = app.state.repo
    row = client.get("/api/shipments").json()["items"][0]
    sid = row["shipment_id"]
    selected = client.get(
        "/api/shipments",
        params=dict(
            search=sid,
            route=row["route_id"],
            vessel=row["vessel"],
            stage=row["stage"],
            risk=row["prediction"]["risk"],
        ),
    ).json()
    assert selected["total"] == 1
    assert (
        client.get("/api/shipments", params={"search": "unknown"}).json()["total"] == 0
    )
    at = service.log(sid)[0].event_available_at.isoformat()
    detail = client.get("/api/shipments/" + sid, params={"as_of": at}).json()
    assert detail["actual_delivery"] is None
    assert all(x["actual"] is None for x in detail["milestones"][1:])
    assert (
        client.get(f"/api/shipments/{sid}/milestones", params={"as_of": at}).json()
        == detail["milestones"]
    )
    assert client.get("/api/shipments/" + sid, params={"historical": True}).json()[
        "actual_delivery"
    ]
    req = dict(shipment_id=sid, as_of=at)
    assert client.post("/api/predict", json=req).json()["stage"] == "origin_departure"
    assert (
        client.post(
            "/api/predict", json={**req, "stage": "customs_clearance_complete"}
        ).status_code
        == 422
    )
    assert client.get("/api/shipments/bad").status_code == 404
    for bad in ["invalid", "2025-07-01T05:00:00"]:
        assert client.get("/api/shipments", params={"as_of": bad}).status_code == 422


def test_gap_and_prediction_updates(client):
    service = app.state.repo
    flags = set()
    for sid in service.plans:
        body = client.get(
            f"/api/shipments/{sid}/propagation",
            params={"as_of": service.end.isoformat()},
        ).json()
        last = None
        for m in body["milestones"]:
            if m["deviation"] is None:
                continue
            if last is not None:
                diff = m["deviation"] - last["deviation"]
                assert m["added"] == pytest.approx(max(diff, 0))
                assert m["recovered"] == pytest.approx(max(-diff, 0))
                assert m["across_gap"] == (m["order"] - last["order"] > 1)
                flags.add("gap" if m["across_gap"] else "continuous")
                flags.add("increase" if diff > 0 else "recovery")
            last = m
        for a, b in zip(body["updates"], body["updates"][1:]):
            assert b["change_from_previous"] == pytest.approx(b["delay"] - a["delay"])
    assert flags == {"gap", "continuous", "increase", "recovery"}


def test_scenario_is_symmetric_and_immutable(client):
    service = app.state.repo
    sid = next(iter(service.plans))
    events = service.log(sid)
    booked = (events[1].scheduled_timestamp - events[0].scheduled_timestamp) / HOUR
    req = dict(
        shipment_id=sid,
        stage=events[0].stage_name,
        as_of=events[0].event_available_at.isoformat(),
    )
    before = client.post("/api/predict", json=req).json()
    baseline = client.post(
        "/api/scenario", json={**req, "expected_hours": booked}
    ).json()
    assert baseline["hypothetical"] and baseline["change_delay"] == 0
    actual = client.post(
        "/api/scenario", json={**req, "expected_hours": booked + 4}
    ).json()
    assert actual["change_delay"] == pytest.approx(
        actual["scenario"]["delay"] - actual["baseline"]["delay"]
    )
    assert (
        client.post("/api/scenario", json={**req, "expected_hours": -2}).status_code
        == 422
    )
    assert client.post("/api/predict", json=req).json() == before
