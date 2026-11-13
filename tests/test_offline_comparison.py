"""Phase 2.1 inference and scoring contracts. Booster artifacts require the experiment extras."""
import json

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyRegressor

from data_generation.config import ROOT
from data_generation.schema import FEATURES
from data_generation.snapshots import EVENT_COLUMNS, features_as_of, planning_view
from ml.comparison_metrics import aligned_predictions, choose, metrics, severe_metrics
from ml.model import eta
from ml.offline_candidates import EXPERIMENTS, OfflineCandidate, anchor, training_target


def test_residual_target_from_observed_anchor():
    f = pd.DataFrame(
        {
            "current_stage_delay_hours": [8.0, -3, np.nan],
            "target_final_delay_hours": [5.0, 1, -2],
        }
    )
    np.testing.assert_equal(training_target(f, "residual").to_numpy(), [-3, 4, -2])
    np.testing.assert_equal(training_target(f, "direct").to_numpy(), [5, 1, -2])
    np.testing.assert_equal(anchor(f).to_numpy(), [8, -3, 0])


def test_negative_adjustment_is_applied_once_and_allows_early_eta():
    x = pd.DataFrame({"current_stage_delay_hours": [1.0, 6.0, np.nan]})
    constant = DummyRegressor(strategy="constant", constant=-3).fit(x, [0, 0, 0])
    residual = OfflineCandidate(EXPERIMENTS["E3"], list(x), constant)
    np.testing.assert_equal(residual.predict(x), [-2, 3, -3])
    direct = OfflineCandidate(EXPERIMENTS["E2"], list(x), constant)
    np.testing.assert_equal(direct.predict(x), [-3, -3, -3])
    booked = pd.Timestamp("2025-06-01T12:00:00Z")
    assert eta(booked, residual.predict(x)[0]) == booked - pd.Timedelta(hours=2)


def sample():
    frame = pd.DataFrame(
        dict(
            shipment_id=["A", "A", "A", "B", "C"],
            voyage_id=["U", "U", "U", "V", "V"],
            target_final_delay_hours=[12.0, 12.0, 12.0, 9.0, 6.0],
        ),
        index=list("abcde"),
    )
    return frame, pd.Series([8.0, 6.0, 3.0, 12.0, -99.0], index=frame.index)


def test_strict_severe_shortfall_and_equal_shipment_weight():
    f, p = sample()
    s = severe_metrics(f, p)
    assert (s["n"], s["shipments"], s["voyages"]) == (4, 2, 2)
    assert s["mean_under"] == pytest.approx((4 + 6 + 9 + 0) / 4)
    assert s["equal_shipment_mean"] == pytest.approx(((4 + 6 + 9) / 3 + 0) / 2)
    assert [s[f"under_over_{h}_pct"] for h in (4, 6, 8)] == [50, 25, 25]
    assert severe_metrics(f.iloc[-1:], p.iloc[-1:])["mean_under"] is None


def test_id_alignment_and_tolerance_boundaries():
    f, p = sample()
    assert metrics(f, p) == metrics(f, p.sort_index(ascending=False))
    actual = metrics(f, p)
    assert [actual[f"within_{h}_pct"] for h in (4, 6, 8)] == [40, 60, 60]
    for bad in [
        p.iloc[:-1],
        pd.concat([p, p.iloc[:1]]),
        p.rename(index={"a": "wrong"}),
        p * float("nan"),
    ]:
        with pytest.raises(ValueError):
            aligned_predictions(f, bad)


def test_selection_gives_priority_to_persistence_mae_and_shortfall():
    def row(error):
        return dict(mae=error, rmse=error, p90=error)

    result = {"E0": row(3), "E2": row(4), "E3": row(2)}
    severe = {"E0": {"mean_under": 2}, "E2": {"mean_under": 1}, "E3": {"mean_under": 3}}
    assert choose(result, severe) == "E0"
    severe["E3"]["mean_under"] = 1
    assert choose(result, severe) == "E3"


@pytest.fixture(scope="module")
def published():
    pytest.importorskip("xgboost")
    pytest.importorskip("catboost")
    directory = ROOT / "models/comparison"
    saved = pd.read_csv(directory / "validation_predictions.csv").set_index(
        "snapshot_id", verify_integrity=True
    )
    base = pd.read_csv(
        ROOT / "data/processed/prediction_snapshots.csv", float_precision="round_trip"
    )
    manifest = pd.read_csv(ROOT / "data/processed/split_manifest.csv")
    validation = base.merge(
        manifest.query("split=='validation'"),
        on=["voyage_id", "shipment_id"],
        validate="many_to_one",
    ).set_index("snapshot_id", verify_integrity=True)
    assert set(validation.index) == set(saved.index)
    return directory, saved, validation.loc[saved.index]


@pytest.mark.parametrize("key", list(EXPERIMENTS))
def test_saved_adapter_schema_alignment_and_round_trip(published, key, tmp_path):
    directory, saved, validation = published
    candidate = joblib.load(directory / f"{key}.joblib")
    assert candidate.columns == FEATURES
    # Inputs can arrive in a different order, with trace and outcome columns alongside them.
    f = validation[validation.columns[::-1]].copy()
    f["target_final_delay_hours"] = 1e6
    observed = candidate.predict(f)
    np.testing.assert_allclose(
        observed, saved[f"{key}_final_delay_hours"], rtol=0, atol=1e-7
    )
    with pytest.raises(KeyError):
        candidate.predict(f.drop(columns=FEATURES[0]))
    joblib.dump(candidate, tmp_path / "clone.joblib")
    np.testing.assert_allclose(
        joblib.load(tmp_path / "clone.joblib").predict(f), observed
    )
    missing = f.iloc[:2].copy()
    missing["current_stage_delay_hours"] = np.nan
    assert np.isfinite(candidate.predict(missing)).all()


def test_future_report_and_sensor_changes_cannot_move_any_candidate(published):
    from data_generation.pipeline import audit_disk

    directory, saved, _ = published
    _, tables, _ = audit_disk(ROOT)
    sid = saved.shipment_id.iloc[0]
    plan = (
        planning_view(
            tables["shipments"].query("shipment_id==@sid"), tables["vessel_voyages"]
        )
        .iloc[0]
        .to_dict()
    )
    events = list(
        tables["milestones"]
        .query("shipment_id==@sid")[EVENT_COLUMNS]
        .itertuples(index=False)
    )
    sensor = next(
        tables["port_call_measurements"]
        .loc[lambda x: x.voyage_id.eq(plan["voyage_id"])]
        .itertuples(index=False)
    )
    at = events[0].event_available_at
    clean = pd.DataFrame([features_as_of(plan, events, sensor, at)])
    future = [events[0]] + [
        e._replace(actual_timestamp=at + pd.Timedelta(days=60)) for e in events[1:]
    ]
    altered = pd.DataFrame(
        [
            features_as_of(
                {**plan, "target_final_delay_hours": 10000},
                future,
                sensor._replace(weather_severity=0.99, congestion_level=0.99),
                at,
            )
        ]
    )
    pd.testing.assert_frame_equal(clean, altered)
    for key in EXPERIMENTS:
        model = joblib.load(directory / f"{key}.joblib")
        np.testing.assert_equal(model.predict(clean), model.predict(altered))


def test_selected_artifact_and_validation_etas(published):
    from ml.model import fingerprint

    directory, saved, valid = published
    decision = json.loads((directory / "selection.json").read_text())
    assert fingerprint(directory / decision["model_file"]) == decision["model_sha256"]
    result = json.loads((directory / "validation_metrics.json").read_text())
    assert decision["recommended"] == choose(result["overall"], result["severe"])
    scheduled = pd.to_datetime(saved.scheduled_arrival, utc=True)
    for k in EXPERIMENTS:
        yhat = saved[f"{k}_final_delay_hours"]
        expected = scheduled + pd.to_timedelta((yhat * 3600).round(), unit="s")
        np.testing.assert_equal(
            expected.to_numpy(),
            pd.to_datetime(saved[f"{k}_predicted_eta"], utc=True).to_numpy(),
        )
        assert result["overall"][k]["mae"] == pytest.approx(
            (yhat - valid.target_final_delay_hours).abs().mean()
        )
