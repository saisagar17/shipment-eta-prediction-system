# System Architecture

## Overview

The Shipment ETA Prediction System combines logistics data processing, model inference, operational delay analysis, and an interactive web application.

The backend manages shipment information and predictions. The frontend provides visual access to shipment journeys, delay calculations, and evaluation results.

## Architecture

```text
Synthetic Logistics Dataset
          |
          v
Data Processing and Validation
          |
          v
Point-in-Time Feature Construction
          |
          v
Saved Forecasting Models
          |
          v
FastAPI Prediction Services
          |
          v
React Dashboard
```

## Main Components

| Component | Responsibility |
|---|---|
| Data generation | Creates shipment schedules, operational events and reporting delays |
| Ground truth | Stores complete physical event timelines |
| Feature construction | Builds features from available observations |
| Machine learning | Estimates final delivery delay |
| Delay propagation | Calculates added delay and recovered time |
| FastAPI | Provides predictions and shipment information |
| React | Displays forecasts, explanations and analysis |
| Model evaluation | Compares prediction methods and operational errors |

## Data Design

The dataset represents cargo consignments transported on vessel voyages.

Multiple shipments can share a vessel voyage and therefore share departure, sailing conditions, and destination-port arrival.

Cargo handling, customs clearance, and inland delivery are shipment-specific.

The data is organized into:

- Vessel voyages
- Shipments
- Tracking milestones
- Port measurements
- Complete ground truth
- Prediction snapshots
- Dataset split assignments

## Prediction Workflow

A shipment forecast follows these steps:

1. Select a shipment and observation time.
2. Retrieve tracking reports available at that time.
3. Retrieve available weather and congestion measurements.
4. Construct the approved prediction features.
5. Calculate the latest known schedule deviation.
6. Generate the operational ETA.
7. Generate comparative model predictions.
8. Return delay magnitude, risk category and explanations.

A prediction never uses tracking information released after its observation time.

## ETA Calculation

The actual schedule deviation at a milestone is:

```text
Stage Delay = Actual Milestone Time - Scheduled Milestone Time
```

The operational ETA is:

```text
Predicted ETA = Scheduled Final Delivery + Current Observed Delay
```

The residual learning models use:

```text
Residual Delay = Final Delay - Current Observed Delay
```

At inference:

```text
Predicted Final Delay =
    Current Observed Delay + Predicted Residual Delay
```

This allows residual models to estimate additional delay or recovery.

## Delay Propagation

For consecutive reported milestones:

```text
Net Delay Change =
    Current Stage Deviation - Previous Reported Deviation
```

A positive change indicates additional delay.

A negative change indicates recovered time.

The system avoids adding cumulative stage deviations together, as this would double-count delays.

If intermediate reports are missing, the calculated change applies to the full interval between available observations.

## Model Serving

The API loads saved forecasting artifacts when the service starts.

The operational method is current-delay persistence.

Available comparison models include:

- Random Forest
- Tuned XGBoost residual regression
- Tuned CatBoost residual regression

All learned models use the approved 28-feature input schema.

Saved artifacts are checked for compatibility and integrity.

## Explainability

The application provides two explanation categories.

### Operational Evidence

Includes:

- Reported schedule deviations
- Added and recovered delay
- Known processing durations
- Available weather and congestion measurements
- Missing report information

### Model-Based Evidence

Includes:

- Feature importance
- Local model feature contributions
- Residual delay estimates
- Comparison with operational persistence

Model feature contributions describe learned associations, not proven causes.

## API Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Service readiness |
| `GET /api/metadata` | Simulation and model metadata |
| `GET /api/dashboard` | Operational overview |
| `GET /api/shipments` | Shipment search and filtering |
| `GET /api/shipments/{id}` | Shipment details |
| `GET /api/shipments/{id}/milestones` | Available milestone information |
| `GET /api/shipments/{id}/propagation` | Stage delay analysis |
| `POST /api/shipments/{id}/advance` | Advance to next available report |
| `POST /api/predict` | Generate ETA prediction |
| `POST /api/scenario` | Hypothetical operational scenario |
| `GET /api/analysis/interactions` | Operational relationships |
| `GET /api/model/comparison` | Validation and test comparisons |
| `GET /api/model/metrics` | Saved model metrics |
| `GET /api/model/features` | Feature information |

Interactive API documentation is available at:

http://127.0.0.1:8036/docs

## Frontend

The React application contains four navigation sections:

1. Dashboard
2. Shipments
3. Delay Analysis
4. Model Performance

Shipment details are displayed within the Shipments section.

The UI retrieves data from FastAPI rather than calculating model predictions in the browser.

## Data Leakage Prevention

The system uses report availability timestamps and independent sensor release times.

It also maintains chronological, voyage-grouped partitions.

All shipments and snapshots belonging to the same voyage remain in the same partition.

Final delivery outcomes are used for model evaluation only after their reporting times.

## Limitations

The operational relationships are based on synthetic simulation assumptions.

Multiple snapshots from one shipment are correlated, and the number of independent voyages is limited.

Live operation would require real tracking feeds, additional historical voyages, monitoring, and prospective evaluation.
