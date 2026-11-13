# Three held-out shipment replays

These examples illustrate three observable patterns in the existing test records. The model was already frozen when the examples were chosen. All clocks are UTC. Positive deviation means late relative to the booked milestone.

From Dashboard, open a demonstration shipment in Shipments. Inspect the prediction at the first released report, advance to the next released milestone and compare the revised ETA. In Delay Analysis, check the signed change and gaps. Return to shipment details for the completed-journey reveal. Model Performance shows population scores.

The row clock is when the report became available. The departure row establishes the starting deviation. Subsequent rows compare with the immediately preceding **reported** stage. For persistence, the signed change in deviation and the change in issued ETA are equal. A missing report issues no update.

## Delay amplification · SHP0218

Chennai → Mumbai → Pune · VG044. Booked final delivery **2025-07-08 02:16:33 UTC**.

| Released at (UTC) | Observable milestone | Deviation (h) | Change / ETA revision (h) | Operational ETA (UTC) |
|---|---|---:|---:|---|
| 2025-07-04 06:34:52 | Departure | +0.35 | Initial | 2025-07-08 02:37:27 |
| 2025-07-07 07:21:00 | Port arrival | +0.56 | +0.21 | 2025-07-08 02:50:12 |
| 2025-07-07 22:12:24 | Port processing | +6.73 | +6.17 | 2025-07-08 09:00:23 |
| 2025-07-08 15:42:54 | Customs clearance | +19.28 | +12.55 | 2025-07-08 21:33:27 |

Port processing took 15.11 h. Between the port arrival and handling reports, the observed deviation grew by 6.17 h to 6.73 h late. The operational ETA moved later by the same interval.

## Partial delay recovery · SHP0236

Singapore → Chennai → Bengaluru · VG048. Booked final delivery **2025-07-30 23:48:51 UTC**.

| Released at (UTC) | Observable milestone | Deviation (h) | Change / ETA revision (h) | Operational ETA (UTC) |
|---|---|---:|---:|---|
| 2025-07-25 06:24:33 | Departure | +0.35 | Initial | 2025-07-31 00:09:48 |
| 2025-07-30 12:02:25 | Port processing | +3.56 | +3.21 across gap | 2025-07-31 03:22:09 |
| 2025-07-30 15:40:32 | Customs clearance | +0.74 | -2.82 | 2025-07-31 00:33:02 |

Customs clearance recovered 2.82 h relative to the preceding report. The shipment was still 0.74 h behind schedule. The operational ETA therefore moved earlier while remaining later than the booking.

## Missing intermediate tracking · SHP0238

Singapore → Chennai → Bengaluru · VG048. Booked final delivery **2025-07-31 00:26:35 UTC**.

| Released at (UTC) | Observable milestone | Deviation (h) | Change / ETA revision (h) | Operational ETA (UTC) |
|---|---|---:|---:|---|
| 2025-07-25 06:24:33 | Departure | +0.35 | Initial | 2025-07-31 00:47:32 |
| 2025-07-30 20:40:43 | Customs clearance | +5.99 | +5.64 across gap | 2025-07-31 06:26:09 |

The customs clearance report followed 2 missing intermediate reports. The deviation changed by +5.64 h over the full observed interval. The records cannot assign portions of that change to ocean transit, handling or customs.

## Completed-journey reveal

Open this comparison after finishing the point-in-time replay. Actual final delivery is the physical inland delivery. Each final delay is actual delivery minus booked delivery. Delivery closes the journey without issuing another forecast.

| Shipment | Last pre-delivery forecast (UTC) | Actual final delivery (UTC) | Final delay (h) |
|---|---|---|---:|
| SHP0218 | 2025-07-08 21:33:27 | 2025-07-08 22:32:28 | +20.27 |
| SHP0236 | 2025-07-31 00:33:02 | 2025-07-30 23:34:57 | -0.23 |
| SHP0238 | 2025-07-31 06:26:09 | 2025-07-31 03:17:19 | +2.85 |

## How the examples were selected

Among test shipments, select the largest positive change during an observed adjacent port-processing interval ending late. Next, select the largest adjacent handling or customs recovery that still ends late. Finally, select the longest run of missing intermediate reports bounded by two reports before delivery. Use distinct IDs in this order. Ties use shipment ID and then milestone order. Selection uses released deviations and the existing split manifest. The generator joins final outcomes only after it has selected the examples.

Run `python scripts/demonstrations.py` from the project root to reproduce this guide and its demonstration catalog. The script checks every held-out report against the saved persistence delay and ETA before writing either file.
