"""Orchestration, versioned metadata and deterministic UTF-8 serialization."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config
from .metadata import data_dictionary, feature_schema
from .observations import observe
from .schema import DATES, PATHS, TABLES
from .simulation import physical_records
from .snapshots import attach_labels, build_snapshots, planning_view, split_manifest
from .validate import check, validate


def generate(cfg: Config):
    schedule, voyage, cargo, observation = [np.random.default_rng(s) for s in np.random.SeedSequence(cfg.seed).spawn(4)]
    v, s, t = physical_records(cfg, schedule, voyage, cargo)
    o, m = observe(v, s, t, cfg, observation)
    features = build_snapshots(planning_view(s, v), o, m)
    f = attach_labels(features, s, cfg.significant_delay_hours)
    return dict(zip(TABLES, (v, s, t, o, m, f, split_manifest(s, v, o))))


def write_csv(frame, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n", na_rep="",
                 float_format="%.12f", date_format="%Y-%m-%dT%H:%M:%SZ")


def write_json(obj, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False)+"\n", encoding="utf-8", newline="\n")


def export(cfg: Config, root: Path):
    from .report import report
    tables = generate(cfg)
    validate(tables, cfg)
    for key, frame in tables.items():
        write_csv(frame, root/PATHS[key])
    meta = root/"data/metadata"
    write_json(cfg.metadata(), meta/"dataset_config.json")
    write_json(feature_schema(), meta/"feature_schema.json")
    write_csv(data_dictionary(), meta/"data_dictionary.csv")
    loaded_cfg, loaded, checks = audit_disk(root)
    path = root/"reports/dataset_validation.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report(loaded_cfg, loaded, checks), encoding="utf-8", newline="\n")
    return tables


def audit_disk(root: Path):
    meta = root/"data/metadata"
    settings = json.loads((meta/"dataset_config.json").read_text(encoding="utf-8"))
    cfg = Config(**{key:settings[key] for key in Config.__dataclass_fields__})
    check(settings == json.loads(json.dumps(cfg.metadata())), "config metadata agrees with implementation")
    check(json.loads((meta/"feature_schema.json").read_text(encoding="utf-8")) == feature_schema(),
          "on-disk feature allowlist and roles")
    pd.testing.assert_frame_equal(pd.read_csv(meta/"data_dictionary.csv"), data_dictionary())
    frames = {}
    for key, filename in PATHS.items():
        frame = pd.read_csv(root/filename, float_precision="round_trip")
        for col in DATES.intersection(frame.columns):
            # Require the explicit UTC serialization used by the generator.
            check(frame[col].dropna().astype(str).str.endswith("Z").all(), "UTC timestamps " + col)
            frame[col] = pd.to_datetime(frame[col], utc=True, format="ISO8601")
        frames[key] = frame
    return cfg, frames, validate(frames, cfg)
