# Shipment ETA model comparison

## Final operational release

Phase 3 serves the frozen Phase 2.2 persistence artifact for all operational ETAs. The original forest and the tuned residual XGBoost and CatBoost models remain available for side-by-side inference. All four use the same released feature row. No further fitting or selection took place.

| Candidate | Validation MAE | Test MAE | Validation RMSE | Test RMSE | Validation severe shortfall | Test severe shortfall |
|---|---:|---:|---:|---:|---:|---:|
| Persistence | 4.829 | 3.619 | 6.466 | 5.306 | 6.580 | 8.665 |
| Random Forest | 5.650 | 3.976 | 6.978 | 5.392 | 6.302 | 8.138 |
| Tuned XGBoost residual | 4.924 | 3.863 | 6.249 | 5.143 | 5.523 | 6.925 |
| Tuned CatBoost residual | 4.912 | 3.786 | 6.297 | 5.163 | 5.743 | 7.645 |

All values are hours. The held-out test set had been inspected earlier in development. The smaller severe-delay shortfall from boosting can matter operationally, but each booster had a higher validation MAE. The [full Phase 2.2 evaluation](tuning_comparison.md) records both partitions, nine candidates, additional metrics, plots and selection hashes. Its references to the live forest describe the application at the end of Phase 2.2.

## Historical Phase 2.1 offline recommendation

**E0 · Current-delay persistence.** Retain persistence. No learned candidate met both operational selection criteria. The lowest validation MAE was 4.829 h for E0. The reference cohort contains 87 snapshots of 25 shipments on 5 voyages. All errors below are measured on the same validation rows.

The strongest learned candidate by MAE was **E4 · CatBoost residual**. Its MAE was 4.930 h versus 4.829 h for persistence. Its P90 absolute error was 10.488 h versus 11.657 h, and mean significant-delay shortfall was 5.529 h versus 6.580 h. It beat persistence on MAE on 2 of 5 validation voyages.

The recommendation rule admits candidates with lower MAE than persistence and no increase in mean significant-delay shortfall. Eligible candidates are ranked by MAE, then shortfall, RMSE, P90 and ID for exact ties. The five voyage-level comparisons below show the sensitivity of the result to which sailings are evaluated.

## Audit of the existing release

The persisted data passed all 8 Phase 1 audit families, including the independent reconstruction of snapshot inputs and target alignment from event clocks. The manifest join was many-to-one. Snapshot IDs and shipment/report-time pairs were unique. Every saved validation forest prediction matched by ID. The forest's fitted imputation medians and category levels matched its training data. The original code fits the preprocessor inside the training pipeline and attaches outcomes only after feature construction. No inconsistency was found.

| Phase 2 method | MAE (h) | RMSE (h) | R² |
| --- | --- | --- | --- |
| Scheduled ETA | 8.285 | 10.404 | -0.191 |
| Current delay | 4.829 | 6.466 | 0.540 |
| Route median | 7.835 | 9.509 | 0.005 |
| Random Forest | 5.650 | 6.978 | 0.464 |

## Experiment design

Fit on 665 snapshots from 175 shipments on 35 training voyages. The candidate matrix uses the same 28 allowlisted inputs across methods. Existing features already encode the last reported deviation, cumulative net additions and recoveries, remaining time, gaps, booked route and released measurements. Identifiers and labels are used for grouping and scoring. No route-target summary is an input to a booster.

| ID | Candidate | Target | Trees |
| --- | --- | --- | --- |
| E0 | Current-delay persistence | baseline | — |
| E1 | Random Forest | direct | 200 |
| E2 | XGBoost direct | direct | 107 |
| E3 | XGBoost residual | residual | 24 |
| E4 | CatBoost residual | residual | 57 |
| E5 | CatBoost direct | direct | 147 |

E2/E5 predict signed final delay. E3/E4 learn the remaining change: final delay minus the latest observed deviation. At inference, add that observed deviation back exactly once. A negative residual represents recovery. A missing anchor falls back to 0 h, the scheduled-deviation baseline. There were 0 missing anchors in validation. Predicted ETA uses the booked final delivery plus the predicted final delay, rounded to the nearest second.

The two booster families share median imputation and unknown-tolerant one-hot encoding for a controlled comparison. Both optimize squared error and monitor MAE. Use depth 3, learning rate 0.04, seed 42, at most 240 trees, and patience 25. The final 5 chronological training voyages (VG031, VG032, VG033, VG034, VG035) supply 97 early-stopping rows. The preceding 568 rows fit the inner preprocessing and model. Their latest delivery report was 2025-05-07T20:26:44+00:00, before the first monitor sailing at 2025-05-18T05:06:25+00:00. Refit preprocessing and each booster on all training voyages at the selected tree count. One fixed configuration per family was used.

## Overall validation performance

Errors are hours. Signed error equals predicted minus actual delay. A negative mean indicates an early bias. Tolerance rates include both endpoints. Each snapshot has equal weight in this table.

| ID | MAE | RMSE | Median AE | P90 AE | R² | Mean signed error | ±4 h (%) | ±6 h (%) | ±8 h (%) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E0 | 4.829 | 6.466 | 3.619 | 11.657 | 0.540 | -1.097 | 56.322 | 73.563 | 81.609 |
| E1 | 5.650 | 6.978 | 4.953 | 11.354 | 0.464 | 0.040 | 43.678 | 62.069 | 75.862 |
| E2 | 5.486 | 6.880 | 4.674 | 11.534 | 0.479 | -0.116 | 40.230 | 65.517 | 77.011 |
| E3 | 4.935 | 6.296 | 3.935 | 10.652 | 0.564 | -0.154 | 50.575 | 71.264 | 82.759 |
| E4 | 4.930 | 6.263 | 4.106 | 10.488 | 0.569 | 0.021 | 49.425 | 73.563 | 82.759 |
| E5 | 5.451 | 6.779 | 4.735 | 11.324 | 0.494 | 0.049 | 43.678 | 65.517 | 77.011 |

Changing XGBoost from direct to residual targeting changed MAE by -0.550 h. The corresponding CatBoost change was -0.522 h. Negative differences favor the residual formulation.

## Significant-delay underprediction

Actual delay must strictly exceed 6 h. Shortfall is max(actual minus predicted, 0), including zero for an overprediction. The population for every row is **36 snapshots, 11 unique shipments and 4 voyages**. Percentages use snapshots as the denominator and count shortfalls strictly above each threshold. The shipment-equal mean first averages within each consignment, then gives each consignment one vote.

| ID | Mean shortfall (h) | Shipment-equal mean (h) | >4 h (%) | >6 h (%) | >8 h (%) |
| --- | --- | --- | --- | --- | --- |
| E0 | 6.580 | 6.798 | 61.111 | 52.778 | 36.111 |
| E1 | 6.302 | 6.563 | 61.111 | 50.000 | 36.111 |
| E2 | 6.274 | 6.409 | 66.667 | 47.222 | 33.333 |
| E3 | 5.644 | 5.736 | 52.778 | 47.222 | 30.556 |
| E4 | 5.529 | 5.657 | 52.778 | 38.889 | 30.556 |
| E5 | 6.065 | 6.219 | 61.111 | 44.444 | 36.111 |

## Stage-wise MAE (hours)

| Group | Snapshots | Shipments | Voyages | E0 | E1 | E2 | E3 | E4 | E5 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| origin_departure | 25 | 25 | 5 | 7.288 | 7.674 | 7.426 | 7.232 | 7.109 | 7.392 |
| port_arrival | 20 | 20 | 4 | 4.824 | 5.829 | 5.579 | 5.141 | 5.109 | 5.296 |
| port_processing_complete | 20 | 20 | 5 | 4.683 | 5.293 | 5.139 | 4.631 | 4.756 | 5.429 |
| customs_clearance_complete | 22 | 22 | 5 | 2.171 | 3.510 | 3.512 | 2.415 | 2.447 | 3.407 |

## Route and voyage sensitivity

Each validation route has only one voyage. Route means are descriptive, and the voyage table identifies the independent groups behind them.

| Group | Snapshots | Shipments | Voyages | E0 | E1 | E2 | E3 | E4 | E5 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R01 | 15 | 4 | 1 | 5.114 | 5.795 | 5.236 | 5.501 | 5.493 | 5.490 |
| R02 | 21 | 6 | 1 | 6.397 | 6.372 | 6.282 | 6.141 | 5.966 | 6.166 |
| R03 | 12 | 5 | 1 | 6.209 | 6.252 | 5.675 | 5.350 | 5.261 | 5.745 |
| R04 | 23 | 6 | 1 | 2.817 | 3.268 | 3.137 | 3.080 | 3.003 | 3.111 |
| R05 | 16 | 4 | 1 | 4.360 | 7.538 | 7.908 | 5.177 | 5.561 | 7.619 |

| Group | Snapshots | Shipments | Voyages | E0 | E1 | E2 | E3 | E4 | E5 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| VG036 | 12 | 5 | 1 | 6.209 | 6.252 | 5.675 | 5.350 | 5.261 | 5.745 |
| VG037 | 15 | 4 | 1 | 5.114 | 5.795 | 5.236 | 5.501 | 5.493 | 5.490 |
| VG038 | 21 | 6 | 1 | 6.397 | 6.372 | 6.282 | 6.141 | 5.966 | 6.166 |
| VG039 | 16 | 4 | 1 | 4.360 | 7.538 | 7.908 | 5.177 | 5.561 | 7.619 |
| VG040 | 23 | 6 | 1 | 2.817 | 3.268 | 3.137 | 3.080 | 3.003 | 3.111 |

## Missing tracking reports and late shipments

A gap means an earlier tracking slot is absent from the visible sequence (missing_event_count > 0). A sensor reading can be unavailable in either group. These descriptive rates reflect the mix of stages as well as missingness.

| Group | Snapshots | Shipments | Voyages | E0 | E1 | E2 | E3 | E4 | E5 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| No tracking gap | 75 | 25 | 5 | 5.002 | 5.779 | 5.711 | 5.159 | 5.125 | 5.739 |
| Tracking gap | 12 | 10 | 4 | 3.748 | 4.839 | 4.074 | 3.536 | 3.708 | 3.655 |

| Group | Snapshots | Shipments | Voyages | E0 | E1 | E2 | E3 | E4 | E5 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| At or below 6 h | 51 | 14 | 4 | 3.036 | 4.609 | 4.490 | 3.658 | 3.732 | 4.466 |
| More than 6 h late | 36 | 11 | 4 | 7.368 | 7.124 | 6.897 | 6.744 | 6.626 | 6.847 |

## Validation feature importance

For E4 (CatBoost residual), shuffle one raw input across validation rows, rerun the complete final-delay adapter, and measure the change in MAE. Values average five seeded shuffles. For residual candidates, shuffling the current deviation changes both the anchor and the model input. Correlated inputs and the small number of independent voyages limit interpretation. The standard deviations describe shuffle variation.

| Input | Mean MAE increase (h) | SD over shuffles (h) |
| --- | --- | --- |
| current_stage_delay_hours | 4.226 | 0.167 |
| planned_duration_hours | 0.039 | 0.024 |
| completed_stage_count | 0.036 | 0.011 |
| snapshot_stage | 0.031 | 0.008 |
| port_processing_delay_hours | 0.020 | 0.006 |
| port_arrival_delay_hours | 0.019 | 0.005 |

## Reproduction and possible integration

From the project root, install `requirements-experiments.txt` in a Python 3.11 environment. Run `python scripts/compare_models.py` followed by `python -m pytest -q`. Artifacts are under `models/comparison/`. `config.json` includes versions, tree counts, data signatures and ordered inputs. `validation_predictions.csv` has a row per snapshot with the observed anchor, actual residual, six signed final-delay predictions and their ETAs. `validation_metrics.json` includes full-precision subgroup and severe results. `selection.json` identifies the recommended artifact and its SHA-256.

All six serialized candidate adapters were reloaded and invoked on inputs reconstructed by the Phase 1 feature builder for every validation trigger. For future integration, an adapter can accept the existing ordered frame and return final-delay hours through `predict`. Use the existing ETA and risk functions downstream. The current FastAPI loader verifies a forest-specific release signature and its explanation routine walks scikit-learn forest trees. A promotion would require an explicit candidate-aware loader, version/cache update and a compatible per-model local explanation (including the observed anchor for a residual model). The prediction input schema can stay as it is. The API currently serves the separate Phase 2 forest.

## Evaluation limits

Phase 2 previously reported test results. That partition is no longer a completely untouched assessment of model development. New candidate selection and comparisons in this report use validation only. Validation is itself selection data, and repeated snapshots share labels, vessel conditions and port calls. A future independent assessment requires prospectively collecting new voyages after the model and decision rule are frozen, with all earlier labels available before the new sailing period. The five validation voyages provide limited evidence about rare delays or generalization to real freight.
