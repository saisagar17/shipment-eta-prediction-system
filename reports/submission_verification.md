# Phase 3 submission verification

| Check | Result |
|---|---|
| Python 3.11.5, pinned environment | 61 passed, including the original dataset, API, inference and Phase 2.2 suites. One dependency deprecation warning came from Starlette TestClient's use of httpx. |
| React component suite | 5 passed |
| Chromium with the real API | 5 passed. The end-to-end replay covered the Dashboard, shipment selection, forecast, next report, changed ETA, propagation, outcome reveal and validation/test comparison. The mobile navigation check ran at 390 px width. |
| TypeScript, ESLint, Vite production build | Passed |
| Inference parity | E0, E1, T1 and T2 reproduced archived forecast delays for all 87 validation and 175 test snapshots. Additional checks verified issued ETA timestamps for all three guided journeys. |
| Release and UI review | The local submission API identified itself as persistence-0abb80a17ca8. The four tabs and all three technical PDF pages were rendered and reviewed. |
| Integrity | 56 existing dataset, model, evaluation-artifact and test files were checked byte-for-byte against the Phase 2.2 archive. |

## Changed files

- `README.md`
- `frontend/playwright.config.ts`
- `frontend/src/Dashboard.tsx`
- `frontend/src/Journey.tsx`
- `frontend/src/Performance.tsx`
- `frontend/src/Shipments.tsx`
- `frontend/src/styles.css`
- `frontend/src/types.ts`
- `frontend/src/ui.tsx`
- `frontend/vite.config.ts`
- `reports/model_comparison.md`
- `reports/Shipment ETA Prediction System - Technical Report.pdf`
- `scripts/technical_report.py`
- `src/backend/main.py`
- `src/backend/schemas.py`
- `src/backend/service.py`

## Added files

- `frontend/e2e/submission.spec.ts`
- `frontend/src/ForecastEvidence.tsx`
- `frontend/src/Interactions.tsx`
- `reports/architecture.md`
- `reports/demonstration_guide.md`
- `reports/demonstrations.json`
- `reports/submission_verification.md`
- `scripts/demonstrations.py`
- `src/backend/forecast_models.py`
- `src/backend/interactions.py`
- `tests/test_forecast_models.py`
- `tests/test_interactions.py`
- `tests/test_submission_api.py`

The submission archive also includes the verified frontend production build in `frontend/dist/`. Setup and repeatable test commands are in the [README](../README.md).
