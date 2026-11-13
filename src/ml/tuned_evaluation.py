"""Separate validation selection and post-freeze held-out evaluation."""
import json
import shutil
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd

from data_generation.config import ROOT
from data_generation.pipeline import write_csv, write_json
from data_generation.snapshots import planning_view, build_snapshots
from data_generation.schema import DATES, PATHS
from .comparison_metrics import aligned_predictions, choose, metrics, severe_metrics
from .model import data_signature, eta, fingerprint
from .offline_candidates import EXPERIMENTS
from .tuning import OUT, SCHEMA, TUNED, partition, voyage_times

NAMES={k:v.name for k,v in {**EXPERIMENTS,**TUNED}.items()}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def paths():
    return {**{k:ROOT/"models/comparison"/f"{k}.joblib" for k in EXPERIMENTS},
            **{k:OUT/k/"candidate.joblib" for k in TUNED}}


def json_read(path):
    return json.loads(path.read_text(encoding="utf8"))


def assert_boundary(first, second):
    if set(first.voyage_id)&set(second.voyage_id) or set(first.shipment_id)&set(second.shipment_id):
        raise ValueError("Groups cross partitions")
    if voyage_times(first).release.max() >= voyage_times(second).start.min():
        raise ValueError("Late label crosses the evaluation cutoff")


def rebuild(frame):
    """Replay only the evaluated shipments using the original planning and tracking views."""
    def read(name):
        raw=pd.read_csv(ROOT/PATHS[name],float_precision="round_trip")
        for col in DATES.intersection(raw.columns):
            raw[col]=pd.to_datetime(raw[col],utc=True)
        return raw
    ships=read("shipments").loc[lambda s:s.shipment_id.isin(frame.shipment_id)]
    plans=planning_view(ships,read("vessel_voyages"))
    log=read("milestones").loc[lambda e:e.shipment_id.isin(plans.shipment_id)]
    sensors=read("port_call_measurements").loc[lambda s:s.voyage_id.isin(plans.voyage_id)]
    replay=build_snapshots(plans,log,sensors).set_index("snapshot_id",verify_integrity=True)
    if set(replay.index)!=set(frame.index):
        raise ValueError("Replay has different trigger IDs")
    cols=json_read(SCHEMA)["approved_input_columns"]
    x=replay.loc[frame.index,cols]
    pd.testing.assert_frame_equal(x,frame[cols],check_exact=False,atol=1e-8,rtol=0)
    return x,frame.shipment_id.map(ships.set_index("shipment_id").scheduled_arrival)


def score_rows(frame, values):
    scores=metrics(frame,values)
    scores["median_signed"]=float((values-frame.target_final_delay_hours).median())
    scores["severe"]=severe_metrics(frame,values)
    return scores


def evaluate(frame, artifacts, split):
    x,scheduled=rebuild(frame)
    records=frame[["shipment_id","voyage_id","route_id","snapshot_stage","prediction_timestamp","target_final_delay_hours"]].copy()
    records["scheduled_delivery"]=scheduled
    stages,shipments,summary=[],[],{}
    for key,path in artifacts.items():
        model=joblib.load(path)
        if model.columns!=list(x.columns):
            raise ValueError(f"{key} has incompatible input contract")
        pred=pd.Series(model.predict(x),index=x.index)
        np.testing.assert_allclose(pred,model.predict(frame[model.columns]),rtol=0,atol=1e-6)
        pred=aligned_predictions(frame,pred)
        records[f"{key}_hours"]=pred
        records[f"{key}_eta"]=[eta(s,v) for s,v in zip(scheduled,pred)]
        summary[key]=score_rows(frame,pred)
        for stage,g in frame.groupby("snapshot_stage"):
            stages.append(dict(candidate=key,stage=stage,**metrics(g,pred.loc[g.index])))
        per_ship=[]
        for sid,g in frame.groupby("shipment_id"):
            error=(pred.loc[g.index]-g.target_final_delay_hours).abs()
            row=dict(candidate=key,shipment_id=sid,voyage_id=g.voyage_id.iloc[0],n=len(g),mae=error.mean(),
                     **{f"within_{h}_pct":100*error.le(h).mean() for h in (4,6,8)})
            per_ship.append(row)
        shipments.extend(per_ship)
        macro=pd.DataFrame(per_ship)[["mae","within_4_pct","within_6_pct","within_8_pct"]].mean()
        last=frame.sort_values("prediction_timestamp").groupby("shipment_id",sort=False).tail(1)
        summary[key]["shipment_equal"]=macro.to_dict()
        summary[key]["last_report_per_shipment"]=metrics(last,pred.loc[last.index])
    directory=OUT/split
    directory.mkdir(parents=True,exist_ok=True)
    write_csv(records.reset_index(),directory/"predictions.csv")
    write_csv(pd.DataFrame(stages),directory/"by_stage.csv")
    write_csv(pd.DataFrame(shipments),directory/"by_shipment.csv")
    write_json(summary,directory/"metrics.json")
    return summary


def freeze():
    artifact_paths=paths()
    digests={k:fingerprint(p) for k,p in artifact_paths.items()}
    if (OUT/"freeze.json").exists():
        verify_freeze()
        return json_read(OUT/"freeze.json")
    signature=data_signature(ROOT)
    if signature!=json_read(ROOT/"models/metadata.json")["data_sha256"]:
        raise ValueError("Dataset changed since Phase 2")
    for key in TUNED:
        config=json_read(OUT/key/"best.json")
        if config["trials"]!=100 or config["signature"]["data"]!=signature:
            raise ValueError("Incomplete or incompatible trained candidate")
    validation=partition("validation")
    assert_boundary(partition("train"),validation)
    scores=evaluate(validation,artifact_paths,"validation")
    prior=json_read(ROOT/"models/comparison/validation_metrics.json")
    for key in EXPERIMENTS:
        for metric,expected in prior["overall"][key].items():
            np.testing.assert_allclose(scores[key][metric],expected,rtol=0,atol=1e-7)
    severe={k:s["severe"] for k,s in scores.items()}
    selected=choose(scores,severe)
    shutil.copyfile(artifact_paths[selected],OUT/"selected.joblib")
    if fingerprint(OUT/"selected.joblib")!=digests[selected]:
        raise RuntimeError("Selected model copy failed verification")
    record=dict(selected=selected,name=NAMES[selected],time_utc=utc_now(),candidate_sha256=digests,
                data_sha256=signature,validation_metrics_sha256=fingerprint(OUT/"validation/metrics.json"),
                selection_rule="Beat persistence on validation MAE with no greater mean significant-delay shortfall. "
                               "Rank eligible candidates by MAE, shortfall, RMSE, P90 and ID; otherwise choose persistence.",
                validation_mae=scores[selected]["mae"],validation_severe_mean=severe[selected]["mean_under"],
                features=json_read(SCHEMA)["approved_input_columns"])
    write_json(record,OUT/"freeze.tmp")
    (OUT/"freeze.tmp").replace(OUT/"freeze.json")
    return record


def verify_freeze():
    record=json_read(OUT/"freeze.json")
    if ({k:fingerprint(p) for k,p in paths().items()}!=record["candidate_sha256"]
        or fingerprint(OUT/"selected.joblib")!=record["candidate_sha256"][record["selected"]]
        or fingerprint(OUT/"validation/metrics.json")!=record["validation_metrics_sha256"]
        or data_signature(ROOT)!=record["data_sha256"]):
        raise ValueError("Frozen model, comparators, validation record or dataset changed")
    return record


def test_frozen():
    frozen=verify_freeze()
    test=partition("test")
    assert_boundary(pd.concat([partition("train"),partition("validation")]),test)
    models=paths()
    models[frozen["selected"]]=OUT/"selected.joblib"
    started=utc_now()
    summary=evaluate(test,models,"test")
    write_json(dict(started_utc=started,finished_utc=utc_now(),selection_file_sha256=fingerprint(OUT/"freeze.json"),
                    evaluated_selected_sha256=fingerprint(OUT/"selected.joblib"),
                    previously_inspected=True,selection_from="validation"),OUT/"test/evaluation_record.json")
    return summary
