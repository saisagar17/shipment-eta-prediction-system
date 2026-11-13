"""Render the Phase 2.2 report and figures from the frozen evaluation outputs."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from data_generation.config import ROOT
from ml.model import fingerprint
from ml.tuned_evaluation import NAMES, json_read, verify_freeze
from ml.tuning import OUT, TUNED

SPLITS = ("validation", "test")
STAGES = {
    "origin_departure": "Departure", "port_arrival": "Port arrival",
    "port_processing_complete": "Port processing", "customs_clearance_complete": "Customs",
}
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "tuning_figures"


def table(headers, rows):
    def line(cells):
        return "| " + " | ".join(map(str, cells)) + " |"
    return "\n".join([line(headers), line(["---"] * len(headers)), *[line(row) for row in rows]])


def draw(scores, stages):
    FIGURES.mkdir(exist_ok=True)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    colors = ("#187168", "#a4551b")
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.4), sharey=True, layout="constrained")
    y = np.arange(len(NAMES))
    for ax, metric, title in zip(axes, ("mae", "mean_under"), ("Overall MAE", "Severe-delay shortfall")):
        series = []
        for split in SPLITS:
            rows = scores[split]
            series.append([rows[k][metric] if metric == "mae" else rows[k]["severe"][metric] for k in NAMES])
        ax.hlines(y, np.minimum(*series), np.maximum(*series), color="#c0c8c7", linewidth=2)
        for split, values, color, marker in zip(SPLITS, series, colors, ("o", "D")):
            ax.scatter(values, y, color=color, marker=marker, s=40, label=split.capitalize(), zorder=3)
        ax.grid(axis="x", alpha=.17)
        ax.set(title=title, xlabel="Hours • lower is better")
    axes[0].set_yticks(y, [f"{k}   {v}" for k, v in NAMES.items()])
    axes[0].invert_yaxis()
    axes[1].legend(loc="upper right", bbox_to_anchor=(1, 1.19), ncol=2, frameon=False)
    fig.savefig(FIGURES / "accuracy_and_shortfall.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.4), sharey=True, layout="constrained")
    matrix = [stages[s].pivot(index="candidate", columns="stage", values="mae").loc[list(NAMES), list(STAGES)] for s in SPLITS]
    limit = max(m.values.max() for m in matrix)
    for ax, m, split in zip(axes, matrix, SPLITS):
        ax.imshow(m, vmin=0, vmax=limit, cmap="Blues", aspect="auto")
        ax.set(title=split.capitalize(), xticks=range(4), xticklabels=STAGES.values())
        ax.tick_params(axis="both", length=0)
        plt.setp(ax.get_xticklabels(), rotation=22, ha="right")
        for i, row in enumerate(m.values):
            for j, value in enumerate(row):
                ax.text(j, i, f"{value:.2f}", ha="center", va="center",
                        color="white" if value > limit*.58 else "#162630")
    axes[0].set_yticks(range(len(NAMES)), [f"{k}   {name}" for k, name in NAMES.items()])
    fig.suptitle("MAE by shipment stage (hours)", fontweight="bold")
    fig.savefig(FIGURES / "stage_mae.png", dpi=160)
    plt.close(fig)


def main():
    frozen = verify_freeze()
    record = json_read(OUT / "test/evaluation_record.json")
    assert record["selection_file_sha256"] == fingerprint(OUT / "freeze.json")
    assert record["evaluated_selected_sha256"] == fingerprint(OUT / "selected.joblib")
    scores = {s: json_read(OUT / s / "metrics.json") for s in SPLITS}
    stages = {s: pd.read_csv(OUT / s / "by_stage.csv") for s in SPLITS}
    configs = {k: json_read(OUT / k / "best.json") for k in TUNED}
    draw(scores, stages)
    selected = frozen["selected"]
    name = NAMES[selected]
    v, t = (scores[s][selected] for s in SPLITS)
    formatted = lambda vals: [f"{v:.3f}" for v in vals]
    paragraphs = [
        "# Shipment ETA • Phase 2.2",
        "## Model decision",
        f"**{name} ({selected})** had the lowest MAE on both splits, {v['mae']:.3f} h on validation and "
        f"{t['mae']:.3f} h on test. The best tuned model by MAE was residual CatBoost "
        f"({scores['validation']['T2']['mae']:.3f} h and {scores['test']['T2']['mae']:.3f} h). "
        "None of the tuned models qualified for final integration under the existing selection rule.",
        "Tuned residual XGBoost produced the smallest mean severe-delay shortfall on both splits. "
        "Compared with persistence, it reduced that shortfall from 6.580 to 5.523 h on validation and "
        "from 8.665 to 6.925 h on test. Its overall MAE increased by 0.095 h and 0.244 h, respectively. "
        "Persistence remains the offline accuracy benchmark. Its severe-delay shortfall limits its use for delay alerts.",
        "**The held-out test set was previously inspected in the project.** Its results describe a fixed historical cohort. "
        "The validation cohort contains only five voyages, and repeated forecasts on the same voyage are correlated. "
        "Differences of a few tenths of an hour have limited evidence of generalizability.",
        "![Overall error and severe-delay shortfall](tuning_figures/accuracy_and_shortfall.png)",
        "## Evaluation protocol",
        "The original manifest assigns 35 voyages (175 shipments, 665 snapshots) to training, 5 voyages "
        "(25 shipments, 87 snapshots) to validation and 10 voyages (50 shipments, 175 snapshots) to test. "
        "Voyages and shipments are disjoint across splits. All ten original dataset and metadata file hashes were verified.",
        "Each Optuna study completed 100 TPE trials with seed 42, 16 startup trials, a single worker and no pruning. "
        "The objective was snapshot-weighted MAE pooled across three later, nonoverlapping five-voyage blocks "
        "(287 out-of-fold snapshots). Each fold fitted its own imputer and categorical encoder using only its fitting rows.",
        "Each booster monitored MAE on five preceding voyages with patience 16. It then refitted on all earlier voyages at "
        "its chosen tree count before predicting the outer block. The full-training refit used the median tree count "
        "from the winning trial's three folds. Random Forest used bounded tree counts and leaf sizes, with bootstrap sampling. "
        "Each earlier group’s latest final-delivery report had to be available before the earliest scheduled or actual "
        "departure in the next group. The same cutoff check guarded the train/validation and validation/test boundaries.",
        table(["Fold", "Inner fit voyages", "Early-stop voyages", "Outer score voyages", "Outer rows",
               "Last refit label (UTC)", "First score start (UTC)"], [
            [i+1, len(f["fit"]), f["monitor"][0]+"–"+f["monitor"][-1], f["score"][0]+"–"+f["score"][-1],
             configs["T1"]["fold_snapshot_counts"][i], f["refit_end"][:19], f["score_start"][:19]]
            for i, f in enumerate(configs["T1"]["folds"])
        ]),
        "Residual regressors predict final delay minus the latest observed stage delay. Inference adds that observed delay "
        "back once, with zero as the missing-value fallback. The direct forest predicts final delay. "
        "All candidates use the original 28-column feature contract. The E-series models below are the archived Phase 2.1 comparators.",
        "## Optimization results",
        "Both boosters searched depths 2–5, learning rates 0.015–0.14 (log), 80–240 trees in steps of 40 and "
        "row fractions 0.65–1. XGBoost also varied child weight 2–18, L1 0.01–3 (log), L2 0.3–20 (log) "
        "and column fraction 0.5–1. CatBoost used depthwise growth, leaf size 3–20, L2 0.5–20 (log), "
        "Bernoulli sampling and feature fraction 0.55–1. The forest searched 60–180 trees in steps of 20, "
        "depth 3–12, leaf size 2–18, feature fraction 0.4–1 and row fraction 0.6–1.",
        table(["Candidate", "Best trial (zero-based)", "CV MAE (h)", "Trees per fold", "Final trees", "Best parameters"], [
            [NAMES[k], c["best_trial"], f"{c['best_cv_mae']:.4f}", ", ".join(map(str, c["fold_tree_counts"])),
             c["refit_params"]["n_estimators"], "[" + k + " best.json](../models/tuning/" + k + "/best.json)"]
            for k, c in configs.items()
        ]),
        "## Selection and freeze",
        "A learned candidate had to lower validation MAE and have no greater mean severe-delay shortfall than persistence. "
        "Eligible candidates were ranked by MAE, shortfall, RMSE, P90 and candidate ID, in that order. "
        "All model artifacts were hashed at selection. The selected artifact was copied, and its SHA-256 was verified "
        "before and after test evaluation. The inference replay reconstructed all validation and test inputs from released "
        "events and produced the same predictions as the stored snapshots within 0.000001 h.",
        f"The selection was frozen at {frozen['time_utc']}. Test scoring began at {record['started_utc']}. "
        f"The selected SHA-256 on both splits was `{record['evaluated_selected_sha256']}`. "
        "[Freeze record](../models/tuning/freeze.json) · [Test evaluation record](../models/tuning/test/evaluation_record.json)",
        "## Candidate comparison",
        "Errors are in hours. R² measures explained variance in signed final delay. "
        "P50 and P90 are absolute-error percentiles. Median signed error uses predicted minus actual. "
        "Shortfall is the mean of max(actual − predicted, 0) over snapshots with actual final delay strictly above 6 h. "
        "A forecast above the actual delay contributes zero. Tolerance percentages include the boundary.",
    ]
    for split in SPLITS:
        result = scores[split]
        severe = result[selected]["severe"]
        paragraphs += [
            "### " + ("Held-out test" if split == "test" else "Validation"),
            f"{result[selected]['n']} snapshots, {result[selected]['shipments']} shipments and {result[selected]['voyages']} voyages. "
            f"The severe cohort contains {severe['n']} snapshots from {severe['shipments']} shipments on {severe['voyages']} voyages.",
            table(["Candidate", "MAE", "RMSE", "R²", "P50", "P90", "Median signed", "Severe shortfall"], [
                [f"{k} · {NAMES[k]}", *formatted([r[c] for c in ("mae","rmse","r2","median","p90","median_signed")]),
                 f"{r['severe']['mean_under']:.3f}"] for k, r in result.items()
            ]),
            table(["ID", "Within ±4 h (%)", "Within ±6 h (%)", "Within ±8 h (%)",
                   "Severe shortfall >4 h (%)", ">6 h (%)", ">8 h (%)"], [
                [k, *[f"{r[f'within_{h}_pct']:.1f}" for h in (4,6,8)],
                 *[f"{r['severe'][f'under_over_{h}_pct']:.1f}" for h in (4,6,8)]] for k, r in result.items()
            ]),
        ]
    paragraphs += [
        "## Accuracy by stage and shipment",
        "Each heatmap cell is MAE among the available reports at that stage. Tracking gaps change the number of "
        "shipments contributing at later stages. Both panels use the same color scale.",
        "![MAE by stage](tuning_figures/stage_mae.png)",
        "The first four columns below average each shipment’s metrics with equal weight. The final column uses only "
        "each shipment’s latest available pre-delivery forecast. Each cell shows validation / held-out test.",
    ]
    rows = []
    for key in NAMES:
        vals = []
        for field in ("mae", "within_4_pct", "within_6_pct", "within_8_pct"):
            vals.append(" / ".join(f"{scores[s][key]['shipment_equal'][field]:.2f}" for s in SPLITS))
        vals.append(" / ".join(f"{scores[s][key]['last_report_per_shipment']['mae']:.2f}" for s in SPLITS))
        rows.append([key, *vals])
    paragraphs += [
        table(["ID", "MAE (h)", "Within ±4 h (%)", "Within ±6 h (%)", "Within ±8 h (%)", "Last forecast MAE (h)"], rows),
        "Stage counts, R², RMSE, percentiles and tolerance accuracy are in the [validation stage file](../models/tuning/validation/by_stage.csv) "
        "and [test stage file](../models/tuning/test/by_stage.csv). Per-shipment errors and tolerance accuracy are in the "
        "[validation shipment file](../models/tuning/validation/by_shipment.csv) and [test shipment file](../models/tuning/test/by_shipment.csv).",
        "## Files and reproduction",
        "Each of T1, T2 and T3 in [models/tuning](../models/tuning/) contains the fitted pipeline and adapter, full Optuna study, "
        "100-row trial export, best parameters and fold details. Both split folders contain keyed delay predictions, predicted UTC ETAs "
        "and complete metrics. The live API still uses its existing Random Forest.",
        "Use Python 3.11 and install `requirements-tuning.txt`. The evaluated environment used Python 3.11.5, "
        "scikit-learn 1.4.2, XGBoost 2.1.4, CatBoost 1.2.8 and Optuna 4.5.0. To reproduce from scratch, use a separate "
        "copy with an empty models/tuning directory and retain the original data, manifest and comparison artifacts. Run from the project root.",
        "```text\npython scripts/tune_models.py\npython scripts/evaluate_tuning.py freeze\npython scripts/evaluate_tuning.py test\npython scripts/report_tuning.py\npython -m pytest -q\n```",
    ]
    (REPORTS / "tuning_comparison.md").write_text("\n\n".join(paragraphs) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
