"""Adapters for the offline comparison. Inputs follow the Phase 1 column contract."""
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from .model import pipeline


@dataclass(frozen=True)
class Experiment:
    name: str
    family: str
    target: str


EXPERIMENTS = {
    "E0": Experiment("Current-delay persistence", "persistence", "baseline"),
    "E1": Experiment("Random Forest", "forest", "direct"),
    "E2": Experiment("XGBoost direct", "xgboost", "direct"),
    "E3": Experiment("XGBoost residual", "xgboost", "residual"),
    "E4": Experiment("CatBoost residual", "catboost", "residual"),
    "E5": Experiment("CatBoost direct", "catboost", "direct"),
}
SEED = 42
MAX_TREES = 240
PATIENCE = 25
INNER_VOYAGES = 5

XGB_PARAMS = dict(
    objective="reg:squarederror",
    eval_metric="mae",
    tree_method="hist",
    max_depth=3,
    learning_rate=0.04,
    min_child_weight=5,
    reg_lambda=3.0,
    subsample=1.0,
    colsample_bytree=1.0,
    random_state=SEED,
    n_jobs=1,
)
CAT_PARAMS = dict(
    loss_function="RMSE",
    eval_metric="MAE",
    depth=3,
    learning_rate=0.04,
    l2_leaf_reg=3.0,
    random_seed=SEED,
    thread_count=1,
    task_type="CPU",
    allow_writing_files=False,
    verbose=False,
)


def anchor(frame):
    """Unreported current deviation defaults to the booked schedule (zero hours)."""
    return frame.current_stage_delay_hours.fillna(0.0).astype(float)


def training_target(frame, kind):
    final = frame.target_final_delay_hours
    return final - anchor(frame) if kind == "residual" else final


@dataclass
class OfflineCandidate:
    experiment: Experiment
    columns: list[str]
    estimator: Any = None

    def predict(self, features):
        """Return signed final delay, including the residual offset exactly once."""
        if not features.columns.is_unique:
            raise ValueError("Feature names must be unique")
        x = features.loc[:, self.columns]
        if self.experiment.family == "persistence":
            return anchor(x).to_numpy()
        values = np.asarray(self.estimator.predict(x), dtype=float)
        if self.experiment.target == "residual":
            values = values + anchor(x).to_numpy()
        return values


def booster(family, trees, stopping=False):
    if family == "xgboost":
        from xgboost import XGBRegressor

        return XGBRegressor(
            **XGB_PARAMS,
            n_estimators=trees,
            early_stopping_rounds=PATIENCE if stopping else None
        )
    from catboost import CatBoostRegressor

    return CatBoostRegressor(**CAT_PARAMS, iterations=trees)


def fit_booster(experiment, schema, train, monitor_voyages):
    """Select tree count inside training, then refit on the full training partition."""
    columns = schema["approved_input_columns"]
    x = train[columns]
    y = training_target(train, experiment.target)
    monitor = train.voyage_id.isin(monitor_voyages)
    inner_prep = pipeline(schema)["prep"]
    inner_x = inner_prep.fit_transform(x[~monitor])
    monitor_x = inner_prep.transform(x[monitor])
    early = booster(experiment.family, MAX_TREES, stopping=True)
    if experiment.family == "xgboost":
        early.fit(
            inner_x, y[~monitor], eval_set=[(monitor_x, y[monitor])], verbose=False
        )
        trees = early.best_iteration + 1
    else:
        early.fit(
            inner_x,
            y[~monitor],
            eval_set=(monitor_x, y[monitor]),
            early_stopping_rounds=PATIENCE,
            use_best_model=True,
        )
        trees = early.get_best_iteration() + 1
    fitted = Pipeline(
        [
            ("prep", pipeline(schema)["prep"]),
            ("regressor", booster(experiment.family, trees)),
        ]
    )
    fitted.fit(x, y)
    return OfflineCandidate(experiment, columns, fitted), int(trees)
