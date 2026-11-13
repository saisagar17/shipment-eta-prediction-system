# Five-minute interview demo

Start on **Dashboard**. Open an attention-list shipment to see the reason it was flagged, then choose **Shipments** and one of the three replay links. Each link resets the simulation clock to the first available departure report. Times below are UTC.

| Shipment | What to do | What the reports establish |
|---|---|---|
| **SHP0218 · Amplification** | Advance through port arrival to port processing. Open **Inspect delay propagation**. | Deviation rises from +0.56 h to +6.73 h. Processing adds 6.17 h, moving the July 8 ETA from 02:50 to 09:00. |
| **SHP0236 · Partial recovery** | Advance to port processing and then customs. Compare the two issued ETAs. | Deviation falls from +3.56 h to +0.74 h. Customs gains 2.82 h, bringing the July 31 ETA forward from 03:22 to 00:33. |
| **SHP0238 · Missing tracking** | Advance from departure directly to customs. Inspect the missing slots and the revisions table. | The +5.64 h change spans two missing reports. Its division across transit, handling and customs is unknown. |

Under **Why This ETA?**, distinguish the measured schedule deviation from the learned models’ estimates of the remaining delay. Switch the comparison model and point out one available or imputed feature. The operational forecast still carries forward the latest observed deviation.

Choose **Reveal completed history** only after explaining the forecast. Compare the last forecast with the actual delivery and return to replay to hide the physical ledger. The [full report-by-report guide](reports/demonstration_guide.md) includes exact timestamps and all three outcomes.

Finish on **Model Performance**. Switch from validation (87 snapshots) to held-out test (175). Persistence had the lowest MAE, 4.829 h and 3.619 h respectively. Tuned residual XGBoost reduced mean severe-delay shortfall from 6.580 to 5.523 h on validation and from 8.665 to 6.925 h on test. Risk bands are delay thresholds. The data are synthetic and the test cohort had been inspected previously.
