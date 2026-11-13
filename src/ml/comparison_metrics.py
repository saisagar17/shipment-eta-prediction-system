"""Compare keyed predictions on the same rows. Hours are signed predicted minus actual."""
import numpy as np
import pandas as pd

from .train import scores


def aligned_predictions(frame, predictions):
    if (
        not frame.index.is_unique
        or not predictions.index.is_unique
        or frame.index.hasnans
        or predictions.index.hasnans
        or len(frame) != len(predictions)
        or not frame.index.isin(predictions.index).all()
    ):
        raise ValueError("Each evaluation snapshot must have exactly one prediction")
    result = predictions.reindex(frame.index)
    if not np.isfinite(result.to_numpy()).all():
        raise ValueError("Every evaluated prediction must be finite")
    return result


def metrics(frame, predictions):
    values = aligned_predictions(frame, predictions)
    error = values - frame.target_final_delay_hours
    return {
        **scores(frame, values.to_numpy()),
        "bias": float(error.mean()),
        **{f"within_{h}_pct": 100 * float(error.abs().le(h).mean()) for h in [4, 6, 8]},
    }


def severe_metrics(frame, predictions):
    values = aligned_predictions(frame, predictions)
    severe = frame.loc[frame.target_final_delay_hours.gt(6)]
    under = (severe.target_final_delay_hours - values.loc[severe.index]).clip(lower=0)
    return dict(
        n=len(severe),
        shipments=severe.shipment_id.nunique(),
        voyages=severe.voyage_id.nunique(),
        mean_under=float(under.mean()) if len(under) else None,
        equal_shipment_mean=float(under.groupby(severe.shipment_id).mean().mean())
        if len(under)
        else None,
        **{
            f"under_over_{h}_pct": 100 * float(under.gt(h).mean())
            if len(under)
            else None
            for h in [4, 6, 8]
        },
    )


def subgroup_metrics(frame, values):
    groups = []
    for category, series in [
        ("stage", frame.snapshot_stage),
        ("route", frame.route_id),
        ("voyage", frame.voyage_id),
        (
            "tracking",
            frame.missing_event_count.gt(0).map(
                {True: "Tracking gap", False: "No tracking gap"}
            ),
        ),
        (
            "delay",
            frame.target_final_delay_hours.gt(6).map(
                {True: "More than 6 h late", False: "At or below 6 h"}
            ),
        ),
    ]:
        for name, rows in frame.groupby(series, sort=False):
            groups.append(
                dict(
                    category=category,
                    group=name,
                    **metrics(rows, values.loc[rows.index]),
                )
            )
    return groups


def choose(overall, severe):
    """Prefer lower MAE and avoid increasing mean shortfall on significant delays."""
    eligible = [
        key
        for key in overall
        if key != "E0"
        and overall[key]["mae"] < overall["E0"]["mae"]
        and severe[key]["mean_under"] <= severe["E0"]["mean_under"]
    ]
    if not eligible:
        return "E0"
    return min(
        eligible,
        key=lambda k: (
            overall[k]["mae"],
            severe[k]["mean_under"],
            overall[k]["rmse"],
            overall[k]["p90"],
            k,
        ),
    )
