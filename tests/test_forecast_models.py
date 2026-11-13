"""The integrated release must reproduce archived forecasts and explain each live row."""
import json

import numpy as np
import pandas as pd
import pytest

from backend.forecast_models import ForecastModels
from backend import forecast_models
from data_generation.config import ROOT


@pytest.fixture(scope="module")
def release():
    columns = json.loads((ROOT / "data/metadata/feature_schema.json").read_text())["approved_input_columns"]
    return ForecastModels(ROOT, columns)


@pytest.fixture(scope="module")
def snapshots():
    return pd.read_csv(
        ROOT / "data/processed/prediction_snapshots.csv", float_precision="round_trip",
    ).set_index("snapshot_id")


@pytest.mark.parametrize("split", ["validation", "test"])
def test_live_release_and_attributions_match_archived_etas(release, snapshots, split):
    archive = pd.read_csv(ROOT / f"models/tuning/{split}/predictions.csv").set_index("snapshot_id")
    frame = snapshots.loc[archive.index, release.columns]
    # All predictions in the frozen archive, including rows with tracking gaps.
    for key, candidate in release.candidates.items():
        np.testing.assert_allclose(candidate.predict(frame), archive[f"{key}_hours"], atol=1e-8, rtol=0)
    examples = list(frame.groupby("snapshot_stage", sort=False).head(1).index)
    examples.append(frame.index[frame.missing_event_count.gt(0)][0])
    for index in examples:
        row = frame.loc[[index]]
        models = release.compare(row)
        assert list(models) == ["E0", "E1", "T1", "T2"]
        assert release.predict(row) == pytest.approx(archive.loc[index, "E0_hours"])
        for key, result in models.items():
            assert result["delay"] == pytest.approx(archive.loc[index, f"{key}_hours"], abs=1e-8)
            factors = result["contributions"]
            contributions = sum(f["hours"] for f in factors)
            assert result["delay"] == pytest.approx(
                (result["anchor_hours"] or 0) + result["base_hours"] + contributions, abs=2e-5
            )
            if key == "E0":
                assert not factors and result["anchor_hours"] == result["delay"]
            else:
                assert set(f["feature"] for f in factors) == set(release.columns)
                assert {f["feature"] for f in factors if f["available"]} == set(row.dropna(axis=1))
                assert result["global_importance"][0]["value"] > 0
            if key in ("T1", "T2"):
                assert result["anchor_hours"] == models["E0"]["delay"]
            if key == "E1":
                assert result["anchor_hours"] is None


def test_all_models_apply_training_missing_value_rules(release, snapshots):
    frame = snapshots.iloc[[0]][release.columns].copy()
    frame["route_id"] = "previously unseen port route"
    frame["current_stage_delay_hours"] = np.nan
    frame["observed_weather_severity"] = np.nan
    results = release.compare(frame)
    assert results["E0"]["delay"] == 0
    for key in ("E1", "T1", "T2"):
        result = results[key]
        assert np.isfinite(result["delay"])
        effects = {f["feature"]: f for f in result["contributions"]}
        assert not effects["current_stage_delay_hours"]["available"]
        assert not effects["observed_weather_severity"]["available"]
        total = result["base_hours"] + sum(f["hours"] for f in effects.values())
        assert result["delay"] == pytest.approx(total, abs=2e-5)


def test_startup_rejects_a_comparator_with_a_different_digest(release, monkeypatch):
    real_digest = forecast_models.fingerprint

    def altered_digest(path):
        return "different" if path.parent.name == "T2" else real_digest(path)

    monkeypatch.setattr(forecast_models, "fingerprint", altered_digest)
    with pytest.raises(ValueError, match="T2 artifact differs"):
        ForecastModels(ROOT, release.columns)
