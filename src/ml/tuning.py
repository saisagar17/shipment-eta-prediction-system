"""Train-only Optuna studies for frozen Phase 2.2 data."""
import json
from dataclasses import dataclass
from pathlib import Path
from importlib.metadata import version

import joblib
import numpy as np
import optuna
import pandas as pd
from catboost import CatBoostRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import Pipeline
from xgboost import XGBRegressor

from data_generation.config import ROOT
from data_generation.pipeline import write_json
from .model import data_signature, fingerprint, pipeline
from .offline_candidates import Experiment, OfflineCandidate, SEED, training_target

OUT = ROOT / "models/tuning"
SCHEMA = ROOT / "data/metadata/feature_schema.json"
TRIALS = 100
PATIENCE = 16
TUNED = {
    "T1": Experiment("Tuned XGBoost residual", "xgboost", "residual"),
    "T2": Experiment("Tuned CatBoost residual", "catboost", "residual"),
    "T3": Experiment("Tuned Random Forest", "forest", "direct"),
}


def partition(split):
    manifest = pd.read_csv(ROOT / "data/processed/split_manifest.csv")
    subset = manifest.loc[manifest.split.eq(split)]
    raw = pd.read_csv(ROOT / "data/processed/prediction_snapshots.csv", float_precision="round_trip")
    frame = raw.merge(subset, on=["voyage_id", "shipment_id"], validate="many_to_one")
    if set(frame.shipment_id) != set(subset.shipment_id):
        raise ValueError(f"Missing {split} shipment in snapshot cohort")
    return frame.set_index("snapshot_id", verify_integrity=True)


def voyage_times(frame):
    fleet = pd.read_csv(ROOT / "data/raw/vessel_voyages.csv").set_index("voyage_id")
    fleet = fleet.loc[frame.voyage_id.unique()].sort_values(["scheduled_departure", "voyage_id"])
    starts = fleet[["scheduled_departure","actual_departure"]].apply(pd.to_datetime, utc=True).min(axis=1)
    messages = pd.read_csv(ROOT / "data/raw/milestones.csv", usecols=["shipment_id","stage_order","event_available_at"])
    labels = messages.loc[messages.stage_order.eq(4)].set_index("shipment_id").event_available_at
    cargo = frame[["shipment_id","voyage_id"]].drop_duplicates()
    cargo["release"] = pd.to_datetime(cargo.shipment_id.map(labels),utc=True)
    if cargo.release.isna().any():
        raise ValueError("A final label lacks its delivery report")
    return pd.DataFrame({"start": starts, "release":cargo.groupby("voyage_id").release.max()}).reindex(fleet.index)


def fold_plan(train):
    times = voyage_times(train)
    ids = list(times.index)
    if len(ids)<25:
        raise ValueError("Calendar needs at least 25 training voyages for this protocol")
    folds = []
    for cut in range(len(ids)-15,len(ids),5):
        fit, monitor, score = ids[:cut-5],ids[cut-5:cut],ids[cut:cut+5]
        fit_end = times.loc[fit,"release"].max()
        monitor_start = times.loc[monitor,"start"].min()
        refit_end = times.loc[fit+monitor,"release"].max()
        score_start = times.loc[score,"start"].min()
        if not fit_end < monitor_start or not refit_end < score_start:
            raise ValueError("A training fold crosses a label-availability boundary")
        folds.append(dict(fit=fit,monitor=monitor,score=score,fit_end=fit_end.isoformat(),
                          monitor_start=monitor_start.isoformat(),refit_end=refit_end.isoformat(),
                          score_start=score_start.isoformat()))
    return folds


@dataclass
class Fold:
    fit_x: np.ndarray
    monitor_x: np.ndarray
    refit_x: np.ndarray
    score_x: np.ndarray
    fit_y: np.ndarray
    monitor_y: np.ndarray
    refit_y: np.ndarray
    score_y: np.ndarray


def prepare_folds(train, schema, plan, target):
    cols = schema["approved_input_columns"]
    result = []
    for block in plan:
        fit, monitor, score = [train.loc[train.voyage_id.isin(block[k])] for k in ("fit","monitor","score")]
        refit = pd.concat([fit,monitor])
        inner, outer = pipeline(schema)["prep"],pipeline(schema)["prep"]
        result.append(Fold(inner.fit_transform(fit[cols]),inner.transform(monitor[cols]),
                           outer.fit_transform(refit[cols]),outer.transform(score[cols]),
                           *[training_target(f,target).to_numpy() for f in (fit,monitor,refit,score)]))
    return result


def suggest(trial, family):
    if family == "forest":
        return dict(n_estimators=trial.suggest_int("n_estimators",60,180,step=20),
                    max_depth=trial.suggest_int("max_depth",3,12),
                    min_samples_leaf=trial.suggest_int("min_samples_leaf",2,18),
                    max_features=trial.suggest_float("max_features",.4,1.0),
                    max_samples=trial.suggest_float("max_samples",.6,1.0))
    params = dict(n_estimators=trial.suggest_int("n_estimators",80,240,step=40),
                  learning_rate=trial.suggest_float("learning_rate",.015,.14,log=True),
                  max_depth=trial.suggest_int("max_depth",2,5),
                  subsample=trial.suggest_float("subsample",.65,1.0))
    if family == "xgboost":
        params.update(min_child_weight=trial.suggest_int("min_child_weight",2,18),
                      reg_lambda=trial.suggest_float("reg_lambda",.3,20.,log=True),
                      reg_alpha=trial.suggest_float("reg_alpha",.01,3.,log=True),
                      colsample_bytree=trial.suggest_float("colsample_bytree",.5,1.0))
    else:
        params.update(min_data_in_leaf=trial.suggest_int("min_data_in_leaf",3,20),
                      l2_leaf_reg=trial.suggest_float("l2_leaf_reg",.5,20.,log=True),
                      rsm=trial.suggest_float("rsm",.55,1.0))
    return params


def estimator(family, params, stopping=False):
    if family=="forest":
        return RandomForestRegressor(**params, random_state=SEED,n_jobs=1,bootstrap=True)
    if family=="xgboost":
        return XGBRegressor(**params,tree_method="hist",objective="reg:squarederror",eval_metric="mae",
                            early_stopping_rounds=PATIENCE if stopping else None,random_state=SEED,n_jobs=1)
    return CatBoostRegressor(**params,loss_function="RMSE",eval_metric="MAE",grow_policy="Depthwise",
                             bootstrap_type="Bernoulli",thread_count=1,random_seed=SEED,
                             allow_writing_files=False,verbose=False)


def fold_score(family, params, fold):
    trees = params["n_estimators"]
    if family != "forest":
        early = estimator(family,params,stopping=True)
        monitor = (fold.monitor_x,fold.monitor_y)
        if family == "xgboost":
            early.fit(fold.fit_x,fold.fit_y,eval_set=[monitor],verbose=False)
            trees = early.best_iteration+1
        else:
            early.fit(fold.fit_x,fold.fit_y,eval_set=monitor,early_stopping_rounds=PATIENCE,use_best_model=True)
            trees = early.get_best_iteration()+1
    model = estimator(family,{**params,"n_estimators":trees})
    model.fit(fold.refit_x,fold.refit_y)
    # Absolute residual error equals final-delay error after adding the same observed anchor.
    errors = np.abs(model.predict(fold.score_x)-fold.score_y)
    return int(trees),float(errors.sum()),len(errors)


def optimize(key,output=OUT):
    schema = json.loads(SCHEMA.read_text())
    train = partition("train")
    plan = fold_plan(train)
    spec = TUNED[key]
    folds = prepare_folds(train,schema,plan,spec.target)
    directory = output / key
    directory.mkdir(parents=True,exist_ok=True)
    checkpoint = directory/"study.joblib"
    signature = dict(data=data_signature(ROOT), source=fingerprint(Path(__file__)),
                     libraries={p:version(p) for p in ["scikit-learn","xgboost","catboost","optuna","numpy","pandas"]})
    if checkpoint.exists():
        study=joblib.load(checkpoint)
        if study.user_attrs["signature"] != signature:
            raise ValueError("Checkpoint differs from current protocol or inputs. Use a fresh output directory.")
    else:
        study=optuna.create_study(study_name=key,direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=SEED,n_startup_trials=16),
            pruner=optuna.pruners.NopPruner())
        study.set_user_attr("signature",signature)
        study.set_user_attr("folds",plan)

    def objective(trial):
        params=suggest(trial,spec.family)
        results=[fold_score(spec.family,params,f) for f in folds]
        trial.set_user_attr("tree_counts",[n for n,_,_ in results])
        trial.set_user_attr("fold_mae",[e/k for _,e,k in results])
        return sum(e for _,e,_ in results)/sum(k for _,_,k in results)

    def save(study, trial):
        tmp=checkpoint.with_suffix(".tmp")
        joblib.dump(study,tmp)
        tmp.replace(checkpoint)
        if (trial.number+1)%25==0:
            print(f"{key} completed {trial.number+1} trials",flush=True)

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    count=len(study.get_trials(states=[optuna.trial.TrialState.COMPLETE]))
    study.optimize(objective,n_trials=TRIALS-count,callbacks=[save],n_jobs=1)
    if len(study.get_trials(states=[optuna.trial.TrialState.COMPLETE]))!=TRIALS:
        raise RuntimeError("Incomplete study")
    best=study.best_trial
    params={**best.params,"n_estimators":int(np.median(best.user_attrs["tree_counts"]))}
    cols=schema["approved_input_columns"]
    fitted=Pipeline([("prep",pipeline(schema)["prep"]),("regressor",estimator(spec.family,params))])
    fitted.fit(train[cols],training_target(train,spec.target))
    candidate=OfflineCandidate(spec,cols,fitted)
    joblib.dump(candidate,directory/"candidate.joblib",compress=3)
    study.trials_dataframe().to_csv(directory/"trials.csv", index=False)
    write_json(dict(key=key,name=spec.name,target=spec.target,seed=SEED,trials=TRIALS,
                    objective="Pooled forward-fold snapshot MAE (hours)",best_trial=best.number,
                    best_cv_mae=best.value,search_params=best.params,refit_params=params,
                    fold_tree_counts=best.user_attrs["tree_counts"],fold_mae=best.user_attrs["fold_mae"],
                    fold_snapshot_counts=[len(f.score_y) for f in folds],folds=plan,
                    feature_columns=cols,signature=signature),directory/"best.json")
    print(f"{key}: finished {TRIALS} trials; CV MAE {best.value:.4f}",flush=True)
