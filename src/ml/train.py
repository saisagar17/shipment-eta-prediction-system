"""Fit the fixed forest and evaluate the frozen holdouts. Run via scripts/train_model.py."""
import json

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.inspection import permutation_importance
from sklearn.metrics import r2_score

from data_generation.config import ROOT
from data_generation.pipeline import audit_disk, write_json
from .model import PARAMETERS, data_signature, fingerprint, pipeline


def scores(frame, predicted):
    actual = frame.target_final_delay_hours.to_numpy()
    error = np.abs(actual - predicted)
    return dict(
        n=len(frame),
        shipments=frame.shipment_id.nunique(),
        voyages=frame.voyage_id.nunique(),
        mae=float(error.mean()),
        rmse=float(np.sqrt(np.mean(error**2))),
        median=float(np.median(error)),
        p90=float(np.quantile(error, 0.9)),
        r2=float(r2_score(actual, predicted)) if len(set(actual)) > 1 else None,
    )


def baselines(train, frame):
    outcomes = train.drop_duplicates("shipment_id")
    median = outcomes.target_final_delay_hours.median()
    by_route = outcomes.groupby("route_id").target_final_delay_hours.median()
    return {
        "Scheduled ETA": np.zeros(len(frame)),
        "Current delay": frame.current_stage_delay_hours.fillna(0).to_numpy(),
        "Route median": frame.route_id.map(by_route).fillna(median).to_numpy(),
    }


def evaluate(train, frame, predicted, physical):
    output = {
        name: scores(frame, pred)
        for name, pred in {
            **baselines(train, frame),
            "Random Forest": predicted,
        }.items()
    }
    subgroups = []

    def add(category, name, mask):
        if mask.any():
            subgroups.append(
                dict(
                    category=category, name=name, **scores(frame[mask], predicted[mask])
                )
            )

    for category, col in [("Stage", "snapshot_stage"), ("Route", "route_id")]:
        for value in frame[col].unique():
            add(category, value, frame[col].eq(value))
    for label, mask in [
        ("Tracking gap", frame.missing_event_count.gt(0)),
        ("No tracking gap", frame.missing_event_count.eq(0)),
        ("Significant delay", frame.target_significant_delay.eq(1)),
        ("Partial recovery", frame.shipment_id.isin(physical["recover"])),
        ("Amplification", frame.shipment_id.isin(physical["amplify"])),
    ]:
        add("Operational", label, mask)
    points = frame[
        [
            "snapshot_id",
            "shipment_id",
            "voyage_id",
            "snapshot_stage",
            "target_final_delay_hours",
        ]
    ].copy()
    points["predicted"] = predicted
    return {
        "comparison": output,
        "subgroups": subgroups,
        "points": points.to_dict("records"),
    }


def train_model(root=ROOT):
    _, tables, _ = audit_disk(root)
    schema = json.loads((root / "data/metadata/feature_schema.json").read_text())
    cols = schema["approved_input_columns"]
    f = tables["prediction_snapshots"].merge(
        tables["split_manifest"],
        on=["shipment_id", "voyage_id"],
        validate="many_to_one",
    )
    train = f[f.split.eq("train")]
    valid = f[f.split.eq("validation")]
    model = pipeline(schema).fit(train[cols], train.target_final_delay_hours)
    imp = permutation_importance(
        model,
        valid[cols],
        valid.target_final_delay_hours,
        scoring="neg_mean_absolute_error",
        random_state=42,
        n_repeats=5,
    )
    importance = sorted(
        [
            dict(feature=c, increase_mae=x, sd=sd)
            for c, x, sd in zip(cols, imp.importances_mean, imp.importances_std)
        ],
        key=lambda row: -row["increase_mae"],
    )
    t = tables["ground_truth_milestones"].sort_values(["shipment_id", "stage_order"])
    previous = t.groupby("shipment_id").stage_delay_hours.shift()
    physical = {
        "recover": t.loc[
            t.stage_delay_hours.gt(0) & t.stage_delay_hours.lt(previous), "shipment_id"
        ],
        "amplify": t.loc[
            previous.gt(0) & t.stage_delay_hours.gt(previous), "shipment_id"
        ],
    }
    metrics = {}
    for name in ["validation", "test"]:
        holdout = f[f.split.eq(name)]
        metrics[name] = evaluate(train, holdout, model.predict(holdout[cols]), physical)
    directory = root / "models"
    directory.mkdir(exist_ok=True)
    joblib.dump(model, directory / "forest.joblib", compress=3)
    digest = fingerprint(directory / "forest.joblib")
    meta = dict(
        version="rf-" + digest[:10],
        model_sha256=digest,
        sklearn=sklearn.__version__,
        data_sha256=data_signature(root),
        parameters=PARAMETERS,
        features=cols,
        train_shipments=train.shipment_id.nunique(),
        train_snapshots=len(train),
        risk_rule="Low at or below 2 h, Moderate above 2 through 6 h, High above 6 h. Qualitative.",
    )
    write_json(meta, directory / "metadata.json")
    write_json(metrics, directory / "metrics.json")
    write_json(importance, directory / "importance.json")
    print(pd.DataFrame(metrics["test"]["comparison"]).T.to_string())
    return model
