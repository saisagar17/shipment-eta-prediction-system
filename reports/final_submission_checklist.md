# Final submission checklist

**Decision: ready for the internship demonstration.** QA used a clean local Git checkout, a newly created Python 3.11.5 environment and a lockfile-based frontend installation with Node 22.17.1 and npm 10.9.2. The operational version reported by the API was `persistence-0abb80a17ca8`.

## Final package verification

QA ran from a separate Windows extraction with the final folder name, **Shipment ETA Prediction System**. A fresh Python 3.11.5 environment installed the pinned requirements, and `python -m pip check` found no broken requirements. Node 22.17.1 and npm 10.9.2 installed the frontend from its lockfile.

| Check | Final package result |
|---|---|
| `python -m pytest -q` | 61 passed with one Starlette test-client deprecation warning. |
| `python -m pytest -q tests/test_forecast_models.py` | 4 passed. All four serving models reproduced the archived validation and test forecasts. |
| `npm test`, `npm run typecheck`, `npm run lint`, `npm run build` | 5 React tests passed. TypeScript, ESLint and the production build succeeded. npm emitted dependency deprecation notices. |
| README startup and live API | FastAPI ran on port 8036 and Vite on 5236. The frontend proxy returned the expected release version. All 14 OpenAPI operations were exercised. Recalculation from the prediction CSVs matched the metrics for nine candidates on each split. |
| `npx playwright test` and three guided replays | 5 Chromium tests passed. All four tabs and three demo shipments worked. Layout and motion preference checks passed at 360, 768 and 1440 px. The API replay verified all nine issued estimates across the three shipments. |
| Technical report | Three A4 pages rendered and visually checked. The PDF title, all 20 validation/test metric pairs in the comparison table and the three shipment IDs were verified against the saved results. |
| Data and artifact integrity | All 10 dataset and metadata files match the earliest archived dataset byte for byte, including prediction snapshots and the split manifest. All 48 data and model files match the tuning, Phase 3 and prior final QA archives. |

Setup was exercised on Windows. The README also provides equivalent macOS and Linux shell commands.

## Earlier clean-checkout and accessibility checks

| Check | Command or procedure | Actual result |
|---|---|---|
| Clean installation | Create a Python 3.11 virtual environment and run `python -m pip install -r requirements-tuning.txt`, then `python -m pip check`. Run `npm ci` in `frontend/`. | Both installations completed. Pip reported no broken requirements. The local Git clone used a Git bundle. |
| Python | `python -m pytest -q` with a JUnit report outside the checkout | **61 passed**. One Starlette deprecation warning concerns the test client's use of httpx. Includes original dataset integrity and reproducibility tests, split and leakage checks, artifact loading, forecast parity, API and scenario tests. Reproducibility tests use temporary fixtures. |
| Frontend | `npm test`, `npm run typecheck`, `npm run lint`, `npm run build` | **5 component tests passed**. TypeScript, ESLint and the Vite production build exited successfully. Component tests exercised loading, errors, retry, shipment links and filtering. |
| Live HTTP | `python -m uvicorn backend.main:app --app-dir src --host 127.0.0.1 --port 8024`. Start Vite on 5194 with `SHIPMENT_API_ORIGIN=http://127.0.0.1:8024`. Compare the exercised method/path pairs with the running OpenAPI schema. | **14/14 application operations exercised successfully**. Covered health, metadata, dashboard, search/list, details, milestones, propagation, advancement, prediction, what-if, interactions, comparative scores, legacy metrics and features. |
| Browser | Against that Vite instance, set `SHIPMENT_E2E_BASE_URL=http://127.0.0.1:5194` and run `npx playwright test` with Chromium. | **5/5 passed** against the real API. An additional walkthrough followed all three guided shipments through prediction, progression, analysis, outcome reveal and both Model Performance partitions. |
| As-of safety | Compare each demo's issued forecasts with archived predictions, release timestamps, milestone changes and final disclosures. | All **9 pre-delivery updates** matched. Later actual events and final delivery stayed hidden during replay. Explicit historical reveal returned the recorded actual delivery for each shipment. |
| Browser accessibility and layout | Check the four routes at 360, 768 and 1440 CSS px. Navigate by keyboard, verify four named tab links, inspect charts and tables, and compare reduced-motion and normal preferences. Run axe-core 4.10.3 on the four desktop route states for WCAG 2.0/2.1 A and AA rules. | All tested widths fit without horizontal page overflow. Keyboard navigation and motion-preference checks passed. The final automated scan reported **zero violations in the tested states**. |

The application still follows the approved mint-gray, white-card, yellow-tab design. QA fixed a 360 px navigation overflow, added chart summaries and table row-header semantics, and removed a redundant decorative chart from keyboard navigation. The [README screenshots](../README.md#application-screenshots) show the four running views.

## Forecasts and evaluation

The four serving artifacts loaded in the pinned environment. Inference tests compared all four models against saved predictions on **87 validation** and **175 held-out test** snapshots. A separate calculation joined shipment IDs to the frozen manifest and recomputed MAE, RMSE, R², median and P90 absolute error, three tolerance rates, and severe-delay shortfall from the saved forecasts for **all nine candidates on both splits**. Stored scores matched within 0.0000001. The live endpoint returned the four serving models' corresponding split scores. A regression test also recomputes the displayed metrics from each partition's prediction CSV.

| Model | MAE, validation / test (h) | Severe shortfall, validation / test (h) |
|---|---:|---:|
| **Persistence, operational default** | **4.829 / 3.619** | 6.580 / 8.665 |
| Original Random Forest | 5.650 / 3.976 | 6.302 / 8.138 |
| Tuned residual XGBoost | 4.924 / 3.863 | **5.523 / 6.925** |
| Tuned residual CatBoost | 4.912 / 3.786 | 5.743 / 7.645 |

The operational ETA adds the latest observed deviation to booked inland delivery. Risk is a threshold on forecast delay. The browser showed the appropriate validation or test values after each partition switch. The held-out test set had been inspected before the Phase 2.2 evaluation. [Full frozen metrics and selection criteria](tuning_comparison.md)

## Interview replays

| Test shipment | Confirmed observation | Actual final delivery after reveal (UTC) |
|---|---|---|
| SHP0218 | Processing increased deviation from +0.56 h to +6.73 h. The ETA moved 6.17 h later. | July 8, 2025 at 22:32:28 |
| SHP0236 | Customs recovered 2.82 h and left 0.74 h of lateness. | July 30, 2025 at 23:34:57 |
| SHP0238 | Two missing reports separated departure and customs. The +5.64 h net change was attributed only to that interval. | July 31, 2025 at 03:17:19 |

## Documentation and public repository

- The [README](../README.md) covers setup, workflow, screenshots, synthetic assumptions, feature availability, delay arithmetic, model selection, explanations and limitations. The [interview guide](../DEMO_GUIDE.md) is the short walkthrough. The [detailed guide](demonstration_guide.md) gives exact clocks.
- The [technical PDF](<Shipment ETA Prediction System - Technical Report.pdf>) contains **three pages**. All three were rendered and visually inspected. Extracted text includes the actual persistence validation/test MAE pair and SHP0218 replay.
- The public checkout includes source, lockfile, configuration example, datasets, manifest, trained artifacts, evaluation records, documentation and screenshots. **48 data and model files** were compared byte-for-byte against the Phase 3 submission. The source archive is generated from Git's committed tree.
- The ignore rules cover environments, credentials and local configuration, caches, build output, browser-test output and ZIPs. Archived test reports were stripped of local hostnames. The tracked-content scan checked common token formats, private-key markers, credential-bearing URLs, password assignments, local user paths and computer names, including decompressed joblib payloads where applicable. The scan produced no findings. Git integrity, tracked file presence and a clean working tree were checked locally.

## Remaining limits

The cohort is synthetic and contains only five validation voyages and ten test voyages. Correlated updates from the same journey limit the independence of the scores. Late-delivery risk bands have no probability calibration. Chromium coverage and automated accessibility checks cover the exercised routes and states; assistive-technology testing with users and cross-browser certification remain outside this submission. The pinned frontend dependency tree emits deprecation notices on installation. Public package-registry access or a populated package cache is needed for first-time setup.
