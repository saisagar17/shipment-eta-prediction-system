"""Render validation numbers from the offline run, including independent group support."""
from .offline_candidates import EXPERIMENTS
from data_generation.report import md_table
from data_generation.config import STAGES


def render_report(config, audit, results, selection):
    overall, severe, groups = (
        results["overall"],
        results["severe"],
        results["subgroups"],
    )
    best, pick = selection["lowest_validation_mae"], selection["recommended"]
    ids = list(EXPERIMENTS)

    def fmt(v):
        return "n/a" if v is None else f"{v:.3f}"

    def columns(table, keys):
        return [[k, *[fmt(table[k][field]) for field in keys]] for k in ids]

    metric_keys = [
        "mae",
        "rmse",
        "median",
        "p90",
        "r2",
        "bias",
        "within_4_pct",
        "within_6_pct",
        "within_8_pct",
    ]
    table = md_table(
        [
            "ID",
            "MAE",
            "RMSE",
            "Median AE",
            "P90 AE",
            "R²",
            "Mean signed error",
            "±4 h (%)",
            "±6 h (%)",
            "±8 h (%)",
        ],
        columns(overall, metric_keys),
    )
    severe_table = md_table(
        [
            "ID",
            "Mean shortfall (h)",
            "Shipment-equal mean (h)",
            ">4 h (%)",
            ">6 h (%)",
            ">8 h (%)",
        ],
        columns(
            severe,
            [
                "mean_under",
                "equal_shipment_mean",
                "under_over_4_pct",
                "under_over_6_pct",
                "under_over_8_pct",
            ],
        ),
    )

    def grouped(category):
        by_group = {}
        for r in groups:
            if r["category"] == category:
                by_group.setdefault(r["group"], {})[r["candidate"]] = r
        ordered = (
            [k for k in STAGES if k in by_group]
            if category == "stage"
            else sorted(by_group)
        )
        return md_table(
            ["Group", "Snapshots", "Shipments", "Voyages", *ids],
            [
                [
                    name,
                    entries["E0"]["n"],
                    entries["E0"]["shipments"],
                    entries["E0"]["voyages"],
                    *[fmt(entries[k]["mae"]) for k in ids],
                ]
                for name in ordered
                for entries in [by_group[name]]
            ],
        )

    methods = md_table(
        ["ID", "Candidate", "Target", "Trees"],
        [
            [
                k,
                exp.name,
                exp.target,
                config["fitted_tree_counts"].get(k, 200 if k == "E1" else "—"),
            ]
            for k, exp in EXPERIMENTS.items()
        ],
    )
    reproduced = audit["validation_baselines"]
    base = md_table(
        ["Phase 2 method", "MAE (h)", "RMSE (h)", "R²"],
        [
            [name, fmt(row["mae"]), fmt(row["rmse"]), fmt(row["r2"])]
            for name, row in reproduced.items()
        ],
    )
    details = (
        f"{pick} reduced MAE by {selection['validation_mae_gain_hours']:.3f} h and "
        f"mean severe shortfall by {selection['severe_mean_underprediction_reduction_hours']:.3f} h versus persistence."
        if pick != "E0"
        else "Retain persistence. No learned candidate met both operational selection criteria."
    )
    voyages = {
        r["group"]: r["mae"]
        for r in groups
        if r["candidate"] == "E0" and r["category"] == "voyage"
    }
    attribution = results["importance_candidate"]
    wins = sum(
        r["mae"] < voyages[r["group"]]
        for r in groups
        if r["candidate"] == attribution and r["category"] == "voyage"
    )
    top = md_table(
        ["Input", "Mean MAE increase (h)", "SD over shuffles (h)"],
        [
            [row["feature"], fmt(row["mean_mae_increase"]), fmt(row["repeat_sd"])]
            for row in results["permutation_importance"][:6]
        ],
    )
    support = severe["E0"]
    return f"""# Shipment ETA model comparison

## Offline recommendation

**{pick} · {EXPERIMENTS[pick].name}.** {details} The lowest validation MAE was {overall[best]["mae"]:.3f} h for {best}. The reference cohort contains {audit["validation_snapshots"]} snapshots of {audit["validation_shipments"]} shipments on {audit["validation_voyages"]} voyages. All errors below are measured on the same validation rows.

The strongest learned candidate by MAE was **{attribution} · {EXPERIMENTS[attribution].name}**. Its MAE was {overall[attribution]["mae"]:.3f} h versus {overall["E0"]["mae"]:.3f} h for persistence. Its P90 absolute error was {overall[attribution]["p90"]:.3f} h versus {overall["E0"]["p90"]:.3f} h, and mean significant-delay shortfall was {severe[attribution]["mean_under"]:.3f} h versus {severe["E0"]["mean_under"]:.3f} h. It beat persistence on MAE on {wins} of {len(voyages)} validation voyages.

The recommendation rule admits candidates with lower MAE than persistence and no increase in mean significant-delay shortfall. Eligible candidates are ranked by MAE, then shortfall, RMSE, P90 and ID for exact ties. The five voyage-level comparisons below show the sensitivity of the result to which sailings are evaluated.

## Audit of the existing release

The persisted data passed all {len(audit["checks"])} Phase 1 audit families, including the independent reconstruction of snapshot inputs and target alignment from event clocks. The manifest join was many-to-one. Snapshot IDs and shipment/report-time pairs were unique. Every saved validation forest prediction matched by ID. The forest's fitted imputation medians and category levels matched its training data. The original code fits the preprocessor inside the training pipeline and attaches outcomes only after feature construction. No inconsistency was found.

{base}

## Experiment design

Fit on {audit["train_snapshots"]} snapshots from {audit["train_shipments"]} shipments on {audit["train_voyages"]} training voyages. The candidate matrix uses the same 28 allowlisted inputs across methods. Existing features already encode the last reported deviation, cumulative net additions and recoveries, remaining time, gaps, booked route and released measurements. Identifiers and labels are used for grouping and scoring. No route-target summary is an input to a booster.

{methods}

E2/E5 predict signed final delay. E3/E4 learn the remaining change: final delay minus the latest observed deviation. At inference, add that observed deviation back exactly once. A negative residual represents recovery. A missing anchor falls back to 0 h, the scheduled-deviation baseline. There were {audit["missing_anchor_count"]} missing anchors in validation. Predicted ETA uses the booked final delivery plus the predicted final delay, rounded to the nearest second.

The two booster families share median imputation and unknown-tolerant one-hot encoding for a controlled comparison. Both optimize squared error and monitor MAE. Use depth 3, learning rate 0.04, seed {config["seed"]}, at most {config["maximum_trees"]} trees, and patience {config["early_stopping_patience"]}. The final {len(audit["monitor_voyages"])} chronological training voyages ({", ".join(audit["monitor_voyages"])}) supply {audit["inner_monitor_rows"]} early-stopping rows. The preceding {audit["inner_fit_rows"]} rows fit the inner preprocessing and model. Their latest delivery report was {audit["inner_last_fit_label"]}, before the first monitor sailing at {audit["first_monitor_start"]}. Refit preprocessing and each booster on all training voyages at the selected tree count. One fixed configuration per family was used.

## Overall validation performance

Errors are hours. Signed error equals predicted minus actual delay. A negative mean indicates an early bias. Tolerance rates include both endpoints. Each snapshot has equal weight in this table.

{table}

Changing XGBoost from direct to residual targeting changed MAE by {overall['E3']['mae']-overall['E2']['mae']:+.3f} h. The corresponding CatBoost change was {overall['E4']['mae']-overall['E5']['mae']:+.3f} h. Negative differences favor the residual formulation.

## Significant-delay underprediction

Actual delay must strictly exceed 6 h. Shortfall is max(actual minus predicted, 0), including zero for an overprediction. The population for every row is **{support["n"]} snapshots, {support["shipments"]} unique shipments and {support["voyages"]} voyages**. Percentages use snapshots as the denominator and count shortfalls strictly above each threshold. The shipment-equal mean first averages within each consignment, then gives each consignment one vote.

{severe_table}

## Stage-wise MAE (hours)

{grouped("stage")}

## Route and voyage sensitivity

Each validation route has only one voyage. Route means are descriptive, and the voyage table identifies the independent groups behind them.

{grouped("route")}

{grouped("voyage")}

## Missing tracking reports and late shipments

A gap means an earlier tracking slot is absent from the visible sequence (missing_event_count > 0). A sensor reading can be unavailable in either group. These descriptive rates reflect the mix of stages as well as missingness.

{grouped("tracking")}

{grouped("delay")}

## Validation feature importance

For {attribution} ({EXPERIMENTS[attribution].name}), shuffle one raw input across validation rows, rerun the complete final-delay adapter, and measure the change in MAE. Values average five seeded shuffles. For residual candidates, shuffling the current deviation changes both the anchor and the model input. Correlated inputs and the small number of independent voyages limit interpretation. The standard deviations describe shuffle variation.

{top}

## Reproduction and possible integration

From the project root, install `requirements-experiments.txt` in a Python 3.11 environment. Run `python scripts/compare_models.py` followed by `python -m pytest -q`. Artifacts are under `models/comparison/`. `config.json` includes versions, tree counts, data signatures and ordered inputs. `validation_predictions.csv` has a row per snapshot with the observed anchor, actual residual, six signed final-delay predictions and their ETAs. `validation_metrics.json` includes full-precision subgroup and severe results. `selection.json` identifies the recommended artifact and its SHA-256.

All six serialized candidate adapters were reloaded and invoked on inputs reconstructed by the Phase 1 feature builder for every validation trigger. For future integration, an adapter can accept the existing ordered frame and return final-delay hours through `predict`. Use the existing ETA and risk functions downstream. The current FastAPI loader verifies a forest-specific release signature and its explanation routine walks scikit-learn forest trees. A promotion would require an explicit candidate-aware loader, version/cache update and a compatible per-model local explanation (including the observed anchor for a residual model). The prediction input schema can stay as it is. The API currently serves the separate Phase 2 forest.

## Evaluation limits

Phase 2 previously reported test results. That partition is no longer a completely untouched assessment of model development. New candidate selection and comparisons in this report use validation only. Validation is itself selection data, and repeated snapshots share labels, vessel conditions and port calls. A future independent assessment requires prospectively collecting new voyages after the model and decision rule are frozen, with all earlier labels available before the new sailing period. The five validation voyages provide limited evidence about rare delays or generalization to real freight.
"""
