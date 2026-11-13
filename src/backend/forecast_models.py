"""Frozen operational forecast and additive explanations on the same released inputs."""
import json
from importlib.metadata import version

import joblib
import numpy as np
import pandas as pd
from catboost import Pool
from xgboost import DMatrix

from ml.model import data_signature, explain, fingerprint
from ml.offline_candidates import anchor


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def residual_attributions(candidate, frame):
    """Group native TreeSHAP values by the original feature before summarizing them."""
    pipeline = candidate.estimator
    prep = pipeline["prep"]
    regressor = pipeline["regressor"]
    encoded = prep.transform(frame[candidate.columns])
    if candidate.experiment.family == "xgboost":
        values = regressor.get_booster().predict(DMatrix(encoded, nthread=1), pred_contribs=True)
    else:
        values = regressor.get_feature_importance(
            Pool(encoded, thread_count=1), type="ShapValues", thread_count=1
        )

    _, _, numeric = prep.transformers_[0]
    _, categorical_prep, categorical = prep.transformers_[1]
    original = list(numeric)
    for name, levels in zip(categorical, categorical_prep["encode"].categories_):
        original.extend([name] * len(levels))
    grouped = pd.DataFrame(values[:, :-1], columns=original, index=frame.index).T.groupby(
        level=0, sort=False
    ).sum().T
    return values[:, -1], grouped


class ForecastModels:
    def __init__(self, root, columns):
        self.columns = list(columns)
        directory = root / "models"
        tuning = directory / "tuning"
        frozen = read_json(tuning / "freeze.json")
        record = read_json(tuning / "test/evaluation_record.json")
        selected_hash = frozen["candidate_sha256"]["E0"]
        if (
            frozen["selected"] != "E0"
            or frozen["features"] != self.columns
            or data_signature(root) != frozen["data_sha256"]
            or record["selection_file_sha256"] != fingerprint(tuning / "freeze.json")
            or record["evaluated_selected_sha256"] != selected_hash
        ):
            raise ValueError("Operational release disagrees with the frozen evaluation")
        libraries = read_json(tuning / "T1/best.json")["signature"]["libraries"]
        for package in ("scikit-learn", "xgboost", "catboost", "numpy", "pandas"):
            installed = version(package)
            if installed != libraries[package]:
                raise ValueError(f"The saved release needs {package} {libraries[package]}, found {installed}")

        self.version = f"persistence-{selected_hash[:12]}"
        self.candidates = {}
        paths = {
            "E0": tuning / "selected.joblib",
            "E1": directory / "comparison/E1.joblib",
            "T1": tuning / "T1/candidate.joblib",
            "T2": tuning / "T2/candidate.joblib",
        }
        for key, path in paths.items():
            if fingerprint(path) != frozen["candidate_sha256"][key]:
                raise ValueError(f"{key} artifact differs from the validation freeze")
            candidate = joblib.load(path)
            if candidate.columns != self.columns:
                raise ValueError(f"{key} feature schema differs from the validation freeze")
            self.candidates[key] = candidate

        self.global_importance = {
            "E0": [],
            "E1": [
                dict(feature=row["feature"], value=row["increase_mae"])
                for row in read_json(directory / "importance.json")
            ],
        }
        manifest = pd.read_csv(root / "data/processed/split_manifest.csv")
        training = manifest[manifest.split.eq("train")][["shipment_id", "voyage_id"]]
        snapshots = pd.read_csv(
            root / "data/processed/prediction_snapshots.csv",
            usecols=["shipment_id", "voyage_id", *self.columns],
            float_precision="round_trip",
        )
        training = snapshots.merge(training, on=["shipment_id", "voyage_id"], validate="many_to_one")
        for key in ("T1", "T2"):
            _, effects = residual_attributions(self.candidates[key], training)
            means = effects.abs().mean().sort_values(ascending=False, kind="stable")
            self.global_importance[key] = [
                dict(feature=name, value=float(value)) for name, value in means.items()
            ]

    def predict(self, frame, key="E0"):
        if len(frame) != 1:
            raise ValueError("A live forecast requires one shipment snapshot")
        return float(self.candidates[key].predict(frame)[0])

    def compare(self, frame):
        if len(frame) != 1:
            raise ValueError("A live comparison requires one shipment snapshot")
        x = frame.loc[:, self.columns]
        observed_delay = float(anchor(x).iloc[0])
        results = {}
        for key, candidate in self.candidates.items():
            offset = observed_delay
            if key == "E0":
                base, factors = 0.0, []
                local_method = "Carry the latest observed deviation through to delivery. A missing deviation uses zero hours."
                global_method = "The operational rule uses the current reported schedule deviation."
            elif key == "E1":
                forest = explain(candidate.estimator, x)
                offset = None
                base, factors = forest["base_hours"], forest["contributions"]
                local_method = "Average change along the forest decision paths for this forecast."
                global_method = "Increase in validation MAE after permuting each input (hours)."
            else:
                bias, effects = residual_attributions(candidate, x)
                base = float(bias[0])
                factors = [
                    dict(feature=name, hours=float(value))
                    for name, value in effects.iloc[0].items()
                ]
                factors.sort(key=lambda row: -abs(row["hours"]))
                local_method = "Native SHAP values explain the residual adjustment to the observed delay (hours)."
                global_method = "Mean absolute SHAP value for the residual across training snapshots (hours)."
            for factor in factors:
                factor["available"] = bool(pd.notna(x.iloc[0][factor["feature"]]))
            results[key] = dict(
                name=candidate.experiment.name,
                delay=self.predict(x, key),
                base_hours=float(base),
                anchor_hours=offset,
                contributions=factors,
                global_importance=self.global_importance[key],
                global_method=global_method,
                local_method=local_method,
            )
        return results
