# Architecture and evidence boundaries

The React client calls a local FastAPI service. The service joins the unchanged manifest to booking plans, timestamped milestone reports and independently released port measurements. The UI fetches new results when the shipment, report or simulation clock changes. Forecasts, evidence, scenarios and scores come from the API.

| Layer | Inputs and responsibilities | Code or evidence |
|---|---|---|
| Replay | The 50 test bookings provide the fleet. A shared voyage supplies common departure and ocean conditions. Handling, customs and inland travel vary by shipment. | `src/backend/service.py`, `data/raw/` |
| As-of features | A stage can enter the 28-column vector only after its report release. Independent sensor clocks gate weather and congestion. Both endpoints are required to measure an interval. | `src/data_generation/snapshots.py`, `data/metadata/feature_schema.json` |
| Inference | Startup checks frozen model digests, data signatures, package versions and feature order. E0 serves the operational ETA. E1, T1 and T2 run as named comparisons. | `src/backend/forecast_models.py`, `models/tuning/freeze.json` |
| Interpretation | The observed ledger computes signed differences from each preceding report. Separate local explanations use forest path changes or booster TreeSHAP values grouped across encoded columns. E0 carries the current observed deviation forward. | `src/ml/propagation.py`, `frontend/src/ForecastEvidence.tsx` |
| Fleet analysis | Report cutoffs also apply to fleet relationships. Congestion pairs are aggregated per voyage. Handling and customs recovery require adjacent reports. Tracking gaps become visible only after a later report. | `src/backend/interactions.py`, `frontend/src/Interactions.tsx` |
| Offline evaluation | Saved validation and test records supply metrics, stage scores and prediction-error charts. Evaluation outcomes appear on Model Performance in aggregate or anonymous points. | `models/tuning/validation/`, `models/tuning/test/`, `frontend/src/Performance.tsx` |

## Clocks and arithmetic

For a released report, **deviation = actual milestone time − booked milestone time**. Each new deviation replaces the previous balance. A positive difference between two observed deviations adds delay. A negative difference gains time. When an intermediate report is missing, the difference applies to the entire visible interval. Only the explicit completed-journey reveal joins the full physical ledger for an individual shipment.

The operational ETA equals booked inland delivery plus the last issued deviation. Both residual models add a learned remaining correction to that same deviation. A learned model’s forecast can be reconstructed from its starting value, signed feature effects and any persistence anchor. Global forest importance measures validation MAE change under permutation. Global booster importance measures mean absolute grouped SHAP values on training rows. Their scales describe different quantities.

The fleet recovery statistic measures the amount of **existing lateness** removed in complete adjacent intervals. In a shipment’s ledger, the signed interval gain can also describe a shipment moving further ahead of schedule. Shipment details label the latter as time gained.

## API entry points

| Request | Result |
|---|---|
| GET `/api/metadata`, `/api/health` | Clock range, version, safe demonstration start points and service readiness |
| GET `/api/dashboard`, `/api/shipments` | Active operational predictions, rule-based risk, attention reasons, search and filtering |
| GET `/api/shipments/{id}` | As-of booking and timeline. Explicit `historical=true` returns the completed physical ledger |
| POST `/api/predict` | Body includes shipment_id and optional as_of and stage. Returns the operational ETA, observed evidence and the four model forecasts |
| POST `/api/shipments/{id}/advance?as_of=…` | Explicitly advances the requested replay to the next available pre-delivery report |
| GET `/api/shipments/{id}/milestones`, `/api/shipments/{id}/propagation` | Release-filtered milestones and each issued ETA revision |
| POST `/api/scenario` | Same forecast trigger and a hypothetical next interval in hours. Both branches use the current released measurements |
| GET `/api/analysis/interactions?as_of=…` | Paired fleet observations with units, denominators and missingness |
| GET `/api/model/comparison?split=validation` or `test` | operational-model comparison, stage scores and chart points |
| GET `/api/model/metrics`, `/api/model/features` | Original forest evaluation and permutation importance for existing clients |

Sparse monitoring, small subgroups and synthetic operating rules limit transfer to live shipments. Prospective evaluation on new voyages is required before assigning alert probabilities or using these rankings to make carrier decisions.
