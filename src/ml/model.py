"""Training-only preprocessing, exact tree-path explanations and artifact compatibility."""
import hashlib
import json

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from data_generation.config import ROOT

PARAMETERS = dict(
    n_estimators=200, max_depth=10, min_samples_leaf=3, random_state=42, n_jobs=1
)


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def data_signature(root):
    return {
        p.relative_to(root).as_posix(): fingerprint(p)
        for p in sorted((root / "data").rglob("*"))
        if p.is_file()
    }


def pipeline(schema):
    cat = schema["categorical_inputs"]
    num = [c for c in schema["approved_input_columns"] if c not in cat]
    prep = ColumnTransformer(
        [
            ("num", SimpleImputer(strategy="median", keep_empty_features=True), num),
            (
                "cat",
                Pipeline(
                    [
                        ("fill", SimpleImputer(strategy="most_frequent")),
                        (
                            "encode",
                            OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                        ),
                    ]
                ),
                cat,
            ),
        ]
    )
    return Pipeline([("prep", prep), ("forest", RandomForestRegressor(**PARAMETERS))])


def load_artifacts(root=ROOT):
    directory = root / "models"
    meta = json.loads((directory / "metadata.json").read_text())
    schema = json.loads((root / "data/metadata/feature_schema.json").read_text())
    if (
        meta["data_sha256"] != data_signature(root)
        or meta["sklearn"] != sklearn.__version__
        or meta["model_sha256"] != fingerprint(directory / "forest.joblib")
    ):
        raise ValueError(
            "Model, library or dataset signature mismatch. Use the documented training environment."
        )
    model = joblib.load(directory / "forest.joblib")
    if list(model.feature_names_in_) != schema["approved_input_columns"]:
        raise ValueError("Approved feature order differs from trained pipeline")
    return model, schema, meta


def risk(delay):
    return "High" if delay > 6 else "Moderate" if delay > 2 else "Low"


def eta(scheduled, hours):
    return pd.Timestamp(scheduled) + pd.Timedelta(seconds=round(float(hours) * 3600))


def explain(model, frame):
    """Mean child-minus-parent values along decision paths, aggregated to original fields."""
    prep = model.named_steps["prep"]
    vector = prep.transform(frame)[0].astype(np.float32)
    _, _, numeric = prep.transformers_[0]
    _, categorical, cats = prep.transformers_[1]
    names = list(numeric)
    for col, levels in zip(cats, categorical["encode"].categories_):
        names.extend([col] * len(levels))
    trees = model["forest"].estimators_
    impact = dict.fromkeys(frame.columns, 0.0)
    base = 0.0
    for estimator in trees:
        t = estimator.tree_
        values = t.value[:, 0, 0]
        base += values[0] / len(trees)
        node = 0
        while t.children_left[node] != -1:
            feature = t.feature[node]
            child = (
                t.children_left[node]
                if vector[feature] <= t.threshold[node]
                else t.children_right[node]
            )
            impact[names[feature]] += (values[child] - values[node]) / len(trees)
            node = child
    return {
        "base_hours": base,
        "contributions": sorted(
            [{"feature": k, "hours": v} for k, v in impact.items()],
            key=lambda x: -abs(x["hours"]),
        ),
    }
