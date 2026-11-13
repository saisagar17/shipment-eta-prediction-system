"""Run Phase 2.1 offline using frozen Phase 1 records and train/validation partitions."""
import json
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

import joblib
import numpy as np
import pandas as pd

from data_generation.config import ROOT
from data_generation.pipeline import audit_disk, write_csv, write_json
from data_generation.snapshots import build_snapshots, planning_view
from .comparison_metrics import choose, metrics, severe_metrics, subgroup_metrics
from .model import data_signature, eta, fingerprint, load_artifacts
from .offline_candidates import (
    CAT_PARAMS,
    EXPERIMENTS,
    INNER_VOYAGES,
    MAX_TREES,
    PATIENCE,
    SEED,
    XGB_PARAMS,
    OfflineCandidate,
    anchor,
    fit_booster,
)
from .train import baselines


def audit(root):
    _, tables, checks = audit_disk(root)
    forest, schema, live = load_artifacts(root)
    f = tables["prediction_snapshots"].merge(
        tables["split_manifest"],
        on=["shipment_id", "voyage_id"],
        how="left",
        validate="many_to_one",
    )
    if (
        f.split.isna().any()
        or f.duplicated(["shipment_id", "prediction_timestamp"]).any()
    ):
        raise ValueError("Incomplete manifest or duplicate prediction trigger")
    f = f.set_index("snapshot_id", verify_integrity=True)
    train = f.loc[f.split.eq("train")].copy()
    valid = f.loc[f.split.eq("validation")].copy()
    cols = schema["approved_input_columns"]
    reference = json.loads((root / "models/metrics.json").read_text())["validation"]
    saved = pd.DataFrame(reference["points"]).set_index(
        "snapshot_id", verify_integrity=True
    )
    if set(saved.index) != set(valid.index):
        raise ValueError("Archived validation cohort differs from the current manifest")
    saved = saved.loc[valid.index]
    keys = ["shipment_id", "voyage_id", "snapshot_stage", "target_final_delay_hours"]
    pd.testing.assert_frame_equal(saved[keys], valid[keys])
    reference_preds = baselines(train, valid)
    reference_preds["Random Forest"] = forest.predict(valid[cols])
    np.testing.assert_allclose(
        reference_preds["Random Forest"], saved.predicted, rtol=0, atol=1e-10
    )
    reproduced = {}
    for name, yhat in reference_preds.items():
        reproduced[name] = metrics(valid, pd.Series(yhat, index=valid.index))
        for metric, expected in reference["comparison"][name].items():
            np.testing.assert_allclose(
                reproduced[name][metric], expected, rtol=0, atol=1e-10
            )
    prep = forest["prep"]
    numeric = prep.transformers_[0][2]
    np.testing.assert_allclose(
        prep.named_transformers_["num"].statistics_,
        train[numeric].median().astype(float),
    )
    for col, levels in zip(
        schema["categorical_inputs"],
        prep.named_transformers_["cat"]["encode"].categories_,
    ):
        np.testing.assert_array_equal(levels, sorted(train[col].dropna().unique()))
    ships = tables["shipments"]
    valid["scheduled_arrival"] = valid.shipment_id.map(
        ships.set_index("shipment_id").scheduled_arrival
    )
    plans = planning_view(
        ships[ships.shipment_id.isin(valid.shipment_id)], tables["vessel_voyages"]
    )
    replayed = build_snapshots(
        plans, tables["milestones"], tables["port_call_measurements"]
    )
    replayed = replayed.set_index("snapshot_id", verify_integrity=True).loc[
        valid.index, cols
    ]
    pd.testing.assert_frame_equal(
        replayed, valid[cols], check_exact=False, atol=1e-9, rtol=0
    )
    fleet = tables["vessel_voyages"].loc[lambda d: d.voyage_id.isin(train.voyage_id)]
    monitor_ids = list(
        fleet.sort_values(["scheduled_departure", "voyage_id"])
        .tail(INNER_VOYAGES)
        .voyage_id
    )
    fit_rows = train.loc[~train.voyage_id.isin(monitor_ids)]
    monitor = fleet[fleet.voyage_id.isin(monitor_ids)]
    deliveries = tables["milestones"].loc[
        lambda d: d.stage_order.eq(4) & d.shipment_id.isin(fit_rows.shipment_id)
    ]
    last_label = deliveries.event_available_at.max()
    first_monitor = min(
        monitor.scheduled_departure.min(), monitor.actual_departure.min()
    )
    if last_label >= first_monitor:
        raise ValueError("Early-stopping split overlaps earlier label availability")
    record = dict(
        checks=checks,
        live_version=live["version"],
        validation_baselines=reproduced,
        train_snapshots=len(train),
        train_shipments=train.shipment_id.nunique(),
        train_voyages=train.voyage_id.nunique(),
        validation_snapshots=len(valid),
        validation_shipments=valid.shipment_id.nunique(),
        validation_voyages=valid.voyage_id.nunique(),
        inner_fit_rows=len(fit_rows),
        inner_monitor_rows=len(train) - len(fit_rows),
        monitor_voyages=monitor_ids,
        inner_last_fit_label=last_label.isoformat(),
        first_monitor_start=first_monitor.isoformat(),
        missing_anchor_count=int(valid.current_stage_delay_hours.isna().sum()),
    )
    return train, valid, replayed, forest, schema, record


def permutation(candidate, frame, rounds=5):
    """Shuffle one raw column on validation and measure MAE change for the final prediction."""
    x = frame[candidate.columns]
    y = frame.target_final_delay_hours.to_numpy()
    base = np.abs(candidate.predict(x) - y).mean()
    rng = np.random.default_rng(SEED)
    permutations = [rng.permutation(len(x)) for _ in range(rounds)]
    result = []
    for col in candidate.columns:
        differences = []
        for order in permutations:
            changed = x.copy()
            changed[col] = x[col].to_numpy()[order]
            differences.append(
                float(np.abs(candidate.predict(changed) - y).mean() - base)
            )
        result.append(
            dict(
                feature=col,
                mean_mae_increase=np.mean(differences),
                repeat_sd=np.std(differences),
            )
        )
    return sorted(result, key=lambda row: -row["mean_mae_increase"])


def run(root=ROOT, output=None):
    from .comparison_report import render_report

    train, valid, replayed, forest, schema, audit_result = audit(root)
    cols = schema["approved_input_columns"]
    output = Path(output or root / "models/comparison")
    output.mkdir(parents=True, exist_ok=True)
    config = dict(
        seed=SEED,
        approved_input_columns=cols,
        categorical_inputs=schema["categorical_inputs"],
        xgboost=XGB_PARAMS,
        catboost=CAT_PARAMS,
        maximum_trees=MAX_TREES,
        early_stopping_patience=PATIENCE,
        inner_monitor_voyages=audit_result["monitor_voyages"],
        libraries={
            key: version(key)
            for key in [
                "scikit-learn",
                "numpy",
                "pandas",
                "joblib",
                "catboost",
                "xgboost",
            ]
        },
        current_delay_fallback_hours=0,
        candidates={k: asdict(v) for k, v in EXPERIMENTS.items()},
        fitted_tree_counts={},
        data_sha256=data_signature(root),
    )
    records = valid[
        [
            "shipment_id",
            "voyage_id",
            "route_id",
            "snapshot_stage",
            "prediction_timestamp",
            "missing_event_count",
            "target_final_delay_hours",
        ]
    ].copy()
    records["scheduled_arrival"] = valid.scheduled_arrival
    records["observed_anchor_hours"] = anchor(valid)
    records["actual_residual_hours"] = valid.target_final_delay_hours - anchor(valid)
    overall, severe, groups = {}, {}, []
    with TemporaryDirectory(dir=output) as scratch:
        scratch = Path(scratch)
        for key, exp in EXPERIMENTS.items():
            if key in ["E0", "E1"]:
                candidate = OfflineCandidate(exp, cols, forest if key == "E1" else None)
            else:
                candidate, trees = fit_booster(
                    exp, schema, train, audit_result["monitor_voyages"]
                )
                config["fitted_tree_counts"][key] = trees
            yhat = pd.Series(candidate.predict(valid[cols]), index=valid.index)
            path = scratch / f"{key}.joblib"
            joblib.dump(candidate, path, compress=3)
            loaded = joblib.load(path)
            np.testing.assert_allclose(
                loaded.predict(replayed), yhat, rtol=0, atol=1e-6
            )
            overall[key] = metrics(valid, yhat)
            severe[key] = severe_metrics(valid, yhat)
            groups.extend(
                dict(candidate=key, **row) for row in subgroup_metrics(valid, yhat)
            )
            records[f"{key}_final_delay_hours"] = yhat
            records[f"{key}_predicted_eta"] = [
                eta(s, h) for s, h in zip(valid.scheduled_arrival, yhat)
            ]
        selected = choose(overall, severe)
        best_mae = min(overall, key=lambda k: overall[k]["mae"])
        most_accurate_ml = min(
            (k for k in overall if k != "E0"), key=lambda k: overall[k]["mae"]
        )
        importance = permutation(
            joblib.load(scratch / f"{most_accurate_ml}.joblib"), valid
        )
        results = dict(
            overall=overall,
            severe=severe,
            subgroups=groups,
            importance_candidate=most_accurate_ml,
            permutation_importance=importance,
        )
        selection = dict(
            recommended=selected,
            lowest_validation_mae=best_mae,
            candidate=asdict(EXPERIMENTS[selected]),
            model_file=f"{selected}.joblib",
            model_sha256=fingerprint(scratch / f"{selected}.joblib"),
            validation_mae_gain_hours=overall["E0"]["mae"] - overall[selected]["mae"],
            severe_mean_underprediction_reduction_hours=severe["E0"]["mean_under"]
            - severe[selected]["mean_under"],
            rule="Admit models beating persistence on MAE with no increase in mean significant-delay shortfall. "
            "Rank eligible models by MAE, then shortfall, RMSE, P90 and ID. Otherwise retain persistence.",
            status="Offline recommendation; serving release is separate.",
        )
        write_json(config, scratch / "config.json")
        write_json(audit_result, scratch / "audit.json")
        write_json(results, scratch / "validation_metrics.json")
        write_json(selection, scratch / "selection.json")
        write_csv(records.reset_index(), scratch / "validation_predictions.csv")
        report = render_report(config, audit_result, results, selection)
        for path in sorted(scratch.iterdir()):
            path.replace(output / path.name)
    return report, selection
