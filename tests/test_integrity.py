import pandas as pd
import pytest

from data_generation.config import ROOT, Config
from data_generation.pipeline import audit_disk
from data_generation.validate import IntegrityError, validate


def test_serialized_dataset():
    _, _, passed = audit_disk(ROOT)
    assert passed


@pytest.mark.parametrize("table,column,replacement", [
    ("shipments","actual_departure",pd.Timestamp("2000-01-01",tz="UTC")),
    ("ground_truth_milestones","added_delay_hours",1000.),
    ("milestones","event_available_at",pd.Timestamp("2000-01-01",tz="UTC")),
    ("split_manifest","split","test"),
    ("prediction_snapshots","known_customs_processing_hours",0.0),
    ("prediction_snapshots","target_final_delay_hours",1000.),
])
def test_audit_rejects_corrupted_record(tables, table, column, replacement):
    damaged = dict(tables)
    damaged[table] = damaged[table].copy()
    damaged[table].loc[0,column] = replacement
    with pytest.raises(IntegrityError):
        validate(damaged, Config())


def test_signed_threshold_at_six():
    from data_generation.snapshots import attach_labels
    ships = pd.DataFrame({"shipment_id":["A","B","C"], "final_delay_hours":[-2,6,6+1/3600],
                          "actual_arrival":pd.Timestamp("2025-01-01",tz="UTC")})
    result = attach_labels(ships[["shipment_id"]],ships,6)
    assert result.target_significant_delay.tolist() == [0,0,1]
