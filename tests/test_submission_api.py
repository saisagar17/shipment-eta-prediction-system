from datetime import datetime

from fastapi.testclient import TestClient
import pandas as pd
import pytest

from backend.main import app
from data_generation.config import ROOT


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as service:
        yield service


def test_demo_replay_uses_selected_forecast_and_gates_observations(client):
    metadata = client.get("/api/metadata").json()
    rows = client.get("/api/shipments", params={"size": 100}).json()["items"]
    assert all(row["stage"] in [*metadata["stages"], "not_started"] for row in rows)
    points = pd.read_csv(ROOT / "models/tuning/test/predictions.csv").set_index("snapshot_id")
    for demo in metadata["demonstrations"]:
        assert set(demo) == {"id", "type", "as_of"}
        sid, now = demo["id"], demo["as_of"]
        last_delay = None
        while True:
            params = {"as_of": now}
            detail = client.get("/api/shipments/" + sid, params=params).json()
            assert detail["actual_delivery"] is None
            assert detail["milestones"][-1]["actual"] is None
            result = client.post("/api/predict", json={"shipment_id": sid, **params}).json()
            assert result["version"] == metadata["version"]
            assert result["delay"] == pytest.approx(result["observed"]["current_stage_delay_hours"])
            stage = metadata["stages"].index(result["stage"])
            saved = points.loc[f"{sid}-{stage}"]
            for key, model in result["comparisons"].items():
                assert model["delay"] == pytest.approx(saved[f"{key}_hours"])
                assert pd.Timestamp(model["predicted_eta"]) == pd.Timestamp(saved[f"{key}_eta"])
            released = {row["stage"] for row in detail["milestones"] if row["released"]}
            assert set(result["reported_conditions"]).issubset(released)
            if last_delay is not None:
                journey = client.get(f"/api/shipments/{sid}/propagation", params=params).json()
                assert journey["updates"][-1]["change_from_previous"] == pytest.approx(result["delay"] - last_delay)
            last_delay = result["delay"]
            next_report = client.post(f"/api/shipments/{sid}/advance", params=params)
            if next_report.status_code == 422:
                break
            next_report.raise_for_status()
            later = next_report.json()["as_of"]
            assert datetime.fromisoformat(later.replace("Z","+00:00")) > datetime.fromisoformat(now.replace("Z","+00:00"))
            now = later
        actual = client.get("/api/shipments/" + sid, params={"historical":True}).json()["actual_delivery"]
        assert pd.Timestamp(actual) == pd.Timestamp(saved.scheduled_delivery) + pd.Timedelta(seconds=round(saved.target_final_delay_hours*3600))


@pytest.mark.parametrize("split", ["validation", "test"])
def test_comparison_endpoint_matches_archive(client, split):
    output = client.get("/api/model/comparison", params={"split":split}).json()
    assert output["selected"] == "E0" and output["previously_inspected_test"]
    scores = output["scores"]
    assert output["split"] == split
    archive = pd.read_csv(ROOT / f"models/tuning/{split}/predictions.csv")
    manifest = pd.read_csv(ROOT / "data/processed/split_manifest.csv")
    assert set(archive.shipment_id) == set(manifest.loc[manifest.split.eq(split), "shipment_id"])
    actual = archive.target_final_delay_hours
    for key in ("E0", "E1", "T1", "T2"):
        assert scores[key]["n"] == len(output["points"])
        error = actual - archive[f"{key}_hours"]
        squared = error.pow(2)
        absolute = error.abs()
        expected = {
            "mae": absolute.mean(), "rmse": squared.mean() ** 0.5,
            "r2": 1 - squared.sum() / (actual - actual.mean()).pow(2).sum(),
            "median": absolute.median(), "p90": absolute.quantile(0.9),
            **{f"within_{hours}_pct": 100 * absolute.le(hours).mean() for hours in (4, 6, 8)},
        }
        for metric, value in expected.items():
            assert scores[key][metric] == pytest.approx(value)
        assert scores[key]["severe"]["mean_under"] == pytest.approx(error[actual > 6].clip(lower=0).mean())
        assert sum(r["n"] for r in output["stages"] if r["candidate"] == key) == len(actual)
