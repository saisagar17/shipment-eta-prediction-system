# Shipment ETA Model Comparison

## Objective

This analysis compares forecasting approaches for estimating final shipment delivery delay.

The models use shipment information available at each prediction moment. The objective is to achieve useful ETA predictions while maintaining consistent handling of missing observations and operational delays.

The evaluated approaches include:

- Current-delay persistence
- Random Forest regression
- XGBoost regression
- CatBoost regression
- Residual delay prediction

## Prediction Methods

### Current-Delay Persistence

The persistence method assumes the latest observed schedule deviation continues through final delivery.

```text
Predicted Final Delay = Current Observed Delay
```

It provides a simple and understandable operational baseline.

### Direct Regression

Direct regression predicts final delivery delay from the available shipment features.

```text
Predicted Final Delay = Model(Features)
```

### Residual Regression

Residual models predict the remaining change in schedule deviation.

```text
Residual Delay = Final Delay - Current Observed Delay
```

At prediction time:

```text
Predicted Final Delay =
    Current Observed Delay + Model(Features)
```

Residual predictions can be positive or negative.

A negative residual represents expected recovery.

## Dataset and Features

The models use the same 28 approved prediction features.

These include:

- Route information
- Cargo category
- Planned journey duration
- Current milestone
- Current observed delay
- Delay additions and recovery
- Remaining planned duration
- Port and customs processing information
- Weather and congestion observations
- Missing-report indicators
- Time since the latest report

Shipment IDs, voyage IDs, hidden simulation outcomes, and future tracking information are not used as ordinary model predictors.

## Evaluation Setup

| Partition | Shipments | Voyages | Snapshots |
|---|---:|---:|---:|
| Training | 175 | 35 | 665 |
| Validation | 25 | 5 | 87 |
| Test | 50 | 10 | 175 |

The partitions are chronological and grouped by voyage.

All snapshots from one shipment remain in the same partition.

Model configuration is selected using training and validation data.

The test results provide an additional recorded comparison, although that cohort was also examined during experimentation.

## Main Model Comparison

All error values are measured in hours.

| Model | Validation MAE | Test MAE | Validation RMSE | Test RMSE |
|---|---:|---:|---:|---:|
| Persistence | **4.829** | **3.619** | 6.466 | 5.306 |
| Random Forest | 5.650 | 3.976 | 6.978 | 5.392 |
| Tuned XGBoost residual | 4.924 | 3.863 | **6.249** | **5.143** |
| Tuned CatBoost residual | 4.912 | 3.786 | 6.297 | 5.163 |

### R² Comparison

| Model | Validation R² | Test R² |
|---|---:|---:|
| Persistence | 0.540 | 0.158 |
| Random Forest | 0.464 | 0.131 |
| Tuned XGBoost residual | **0.570** | **0.209** |
| Tuned CatBoost residual | 0.564 | 0.203 |

Persistence achieves the lowest MAE on both partitions.

The tuned boosting models achieve lower squared-error values in some comparisons.

A higher R² does not necessarily imply a lower average absolute ETA error.

## Significant-Delay Underprediction

A significant delay is defined as actual final delivery more than six hours late.

Underprediction is measured as:

```text
Underprediction = max(Actual Delay - Predicted Delay, 0)
```

| Model | Validation mean shortfall | Test mean shortfall |
|---|---:|---:|
| Persistence | 6.580 h | 8.665 h |
| Random Forest | 6.302 h | 8.138 h |
| Tuned XGBoost residual | **5.523 h** | **6.925 h** |
| Tuned CatBoost residual | 5.743 h | 7.645 h |

Tuned XGBoost provides the lowest mean severe-delay shortfall among these methods.

This result is useful because underestimating a large delay can create operational problems.

However, the number of significantly delayed independent shipments is small, so the differences should be interpreted cautiously.

## Accuracy Across Shipment Stages

Prediction errors vary depending on when a forecast is issued.

At departure, many future disruptions are still unknown.

At later milestones, additional operational information becomes available.

The evaluation reports separate results for:

- Departure
- Port arrival
- Port processing
- Customs clearance

Stage-level results are available in:

- `models/tuning/validation/by_stage.csv`
- `models/tuning/test/by_stage.csv`

Later-stage predictions are often more accurate, although not every shipment improves at every observation.

## Missing Tracking

The prediction pipeline supports unavailable reports and measurements.

Missing numerical values are handled by the fitted preprocessing pipeline.

The operational persistence baseline uses a documented fallback if no observed deviation is available.

Features are reconstructed from actual report availability rather than future ground truth.

## Feature Importance

The latest observed stage delay is the most influential predictor in the existing learned-model evaluations.

This explains why persistence performs competitively.

Other useful features include:

- Planned journey duration
- Completed milestone count
- Stage identity
- Port processing deviation
- Remaining duration

Feature importance describes how strongly an input influences model predictions.

It does not establish a causal relationship.

## Forecasting Method Used by the Application

Current-delay persistence is the default operational forecast.

It was selected because it achieved the lowest validation MAE.

Random Forest, tuned XGBoost residual, and tuned CatBoost residual remain available for comparative analysis.

A model comparison selector can be used to inspect alternative predictions without changing the operational ETA.

## Interpretation

The findings highlight an important characteristic of shipment ETA prediction.

The latest observed schedule deviation already contains substantial information about the likely final delay.

Machine learning can improve some aspects of forecasting, particularly larger errors or expected downstream changes, without necessarily outperforming a simple operational rule on average absolute error.

For this dataset, persistence is a reasonable operational choice.

## Limitations

The results come from a small synthetic dataset.

Multiple snapshots from one shipment share a final outcome, and shipments on the same voyage have correlated conditions.

Real-world deployment would require validation on independently collected shipment data.

The comparisons should not be interpreted as evidence of general performance across shipping networks.
