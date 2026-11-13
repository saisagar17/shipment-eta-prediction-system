"""Check the saved Phase 2.2 studies, chronology, model freeze and inference outputs."""
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
import pytest

pytest.importorskip("optuna")
from optuna.trial import TrialState

from ml import tuning
from ml.comparison_metrics import choose
from ml.model import eta, fingerprint
from ml.tuned_evaluation import json_read, verify_freeze
from ml.tuning import OUT, TUNED, fold_plan, partition


def test_fold_plan_is_grouped_and_rejects_unavailable_labels(monkeypatch):
    frame = partition("train")
    times = tuning.voyage_times(frame)
    plan = fold_plan(frame)
    seen = set()
    for fold in plan:
        fit, monitor, score = (set(fold[key]) for key in ("fit", "monitor", "score"))
        assert not (fit & monitor or fit & score or monitor & score or score & seen)
        seen.update(score)
        assert times.loc[list(fit), "release"].max() < times.loc[list(monitor), "start"].min()
        assert times.loc[list(fit | monitor), "release"].max() < times.loc[list(score), "start"].min()
        assert len(score) == len(monitor) == 5
    assert len(seen) == 15
    first = plan[0]
    times.loc[first["fit"][0], "release"] = times.loc[first["monitor"], "start"].min()
    monkeypatch.setattr(tuning, "voyage_times", lambda frame: times)
    with pytest.raises(ValueError, match="label-availability"):
        fold_plan(frame)


@pytest.mark.parametrize("candidate", list(TUNED))
def test_study_exports_100_scored_trials_and_matching_refit(candidate):
    path = OUT / candidate
    study = joblib.load(path / "study.joblib")
    config = json_read(path / "best.json")
    csv = pd.read_csv(path / "trials.csv")
    assert len(csv) == len(study.trials) == config["trials"] == 100
    assert csv["state"].eq("COMPLETE").all()
    assert all(trial.state == TrialState.COMPLETE for trial in study.trials)
    for trial in study.trials:
        assert trial.value == pytest.approx(np.average(
            trial.user_attrs["fold_mae"], weights=config["fold_snapshot_counts"]
        ))
    assert config["best_trial"] == study.best_trial.number
    assert config["best_cv_mae"] == pytest.approx(csv.value.min())
    assert config["search_params"] == study.best_trial.params
    assert config["refit_params"]["n_estimators"] == int(np.median(config["fold_tree_counts"]))
    assert config["folds"] == fold_plan(partition("train"))


def test_frozen_hash_and_validation_only_selection():
    frozen = verify_freeze()
    scores = json_read(OUT / "validation/metrics.json")
    assert frozen["selected"] == choose(scores, {k: v["severe"] for k, v in scores.items()})
    test_run = json_read(OUT / "test/evaluation_record.json")
    assert test_run["previously_inspected"]
    assert test_run["selection_file_sha256"] == fingerprint(OUT / "freeze.json")
    assert test_run["evaluated_selected_sha256"] == frozen["candidate_sha256"][frozen["selected"]]
    assert datetime.fromisoformat(test_run["started_utc"]) > datetime.fromisoformat(frozen["time_utc"])


@pytest.mark.parametrize("split", ["validation", "test"])
def test_inference_reloads_and_matches_exported_eta_and_metrics(split):
    directory = OUT / split
    frame = partition(split)
    records = pd.read_csv(directory / "predictions.csv").set_index("snapshot_id").loc[frame.index]
    assert len(records) == len(frame)
    results = json_read(directory / "metrics.json")
    stages = pd.read_csv(directory / "by_stage.csv")
    shipments = pd.read_csv(directory / "by_shipment.csv")
    selected = json_read(OUT / "freeze.json")["selected"]
    artifacts = {key: OUT / key / "candidate.joblib" for key in TUNED}
    artifacts[selected] = OUT / "selected.joblib"
    for key, path in artifacts.items():
        fitted = joblib.load(path)
        pred = fitted.predict(frame[fitted.columns])
        np.testing.assert_allclose(pred, records[f"{key}_hours"], rtol=0, atol=1e-9)
        expected_eta = pd.to_datetime([eta(t, h) for t, h in zip(records.scheduled_delivery, pred)], utc=True)
        assert expected_eta.equals(pd.DatetimeIndex(pd.to_datetime(records[f"{key}_eta"], utc=True)))
        error = frame.target_final_delay_hours - pred
        severe = error[frame.target_final_delay_hours > 6].clip(lower=0)
        assert severe.mean() == pytest.approx(results[key]["severe"]["mean_under"])
        by_ship = error.abs().groupby(frame.shipment_id).mean()
        saved = shipments[shipments.candidate == key].set_index("shipment_id").loc[by_ship.index]
        np.testing.assert_allclose(by_ship, saved.mae)
        assert by_ship.mean() == pytest.approx(results[key]["shipment_equal"]["mae"])
        by_stage = stages[stages.candidate == key]
        assert by_stage.n.sum() == len(frame)
        assert np.average(by_stage.mae, weights=by_stage.n) == pytest.approx(error.abs().mean())
