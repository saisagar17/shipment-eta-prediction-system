"""Recalculate held-out comparisons using the stored model without fitting it."""
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from data_generation.config import ROOT
from data_generation.pipeline import audit_disk
from ml.model import load_artifacts
from ml.train import baselines, scores

if __name__ == "__main__":
    model, schema, _ = load_artifacts()
    _, tables, _ = audit_disk(ROOT)
    f = tables["prediction_snapshots"].merge(
        tables["split_manifest"],
        on=["shipment_id", "voyage_id"],
        validate="many_to_one",
    )
    reference = json.loads((ROOT / "models/metrics.json").read_text())
    for split in ["validation", "test"]:
        group = f[f.split.eq(split)]
        predictions = baselines(f[f.split.eq("train")], group)
        predictions["Random Forest"] = model.predict(
            group[schema["approved_input_columns"]]
        )
        result = {k: scores(group, p) for k, p in predictions.items()}
        for name, row in result.items():
            for metric, value in row.items():
                np.testing.assert_allclose(
                    value,
                    reference[split]["comparison"][name][metric],
                    rtol=0,
                    atol=1e-10,
                )
        print(split.upper())
        print(pd.DataFrame(result).T.round(3).to_string())
