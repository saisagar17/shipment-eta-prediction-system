# Shipment Journey Examples

This guide presents three shipments that demonstrate delay amplification, partial recovery, and missing tracking observations.

All examples are taken from the existing test dataset. All timestamps use UTC.

The operational ETA is calculated by adding the latest observed stage deviation to the scheduled final delivery time.

## Example 1 — Delay Amplification

**Shipment:** SHP0218

**Route:** Chennai → Mumbai → Pune

**Voyage:** VG044

**Scheduled delivery:** July 8, 2025, 02:16:33 UTC

| Report available | Milestone | Stage delay | Updated ETA |
|---|---|---:|---|
| Jul 4, 06:34:52 | Departure | +0.35 h | Jul 8, 02:37:27 |
| Jul 7, 07:21:00 | Port arrival | +0.56 h | Jul 8, 02:50:12 |
| Jul 7, 22:12:24 | Port processing | +6.73 h | Jul 8, 09:00:23 |
| Jul 8, 15:42:54 | Customs clearance | +19.28 h | Jul 8, 21:33:27 |

Between port arrival and port processing:

```text
Additional Delay = 6.73 - 0.56
                 = 6.17 hours
```

The increase in observed deviation causes the predicted ETA to move later by approximately 6.17 hours.

Port processing lasted approximately 15.11 hours.

### Final Outcome

Actual delivery:

**July 8, 2025, 22:32:28 UTC**

Final delay:

**+20.27 hours**

The example demonstrates how successive operational delays affect delivery forecasts.

## Example 2 — Partial Delay Recovery

**Shipment:** SHP0236

**Route:** Singapore → Chennai → Bengaluru

**Voyage:** VG048

**Scheduled delivery:** July 30, 2025, 23:48:51 UTC

| Report available | Milestone | Stage delay | Updated ETA |
|---|---|---:|---|
| Jul 25, 06:24:33 | Departure | +0.35 h | Jul 31, 00:09:48 |
| Jul 30, 12:02:25 | Port processing | +3.56 h | Jul 31, 03:22:09 |
| Jul 30, 15:40:32 | Customs clearance | +0.74 h | Jul 31, 00:33:02 |

Between port processing and customs clearance:

```text
Recovered Time = 3.56 - 0.74
               = 2.82 hours
```

The shipment recovered part of its accumulated lateness.

Its expected delivery moved earlier, although the shipment remained behind schedule.

### Final Outcome

Actual delivery:

**July 30, 2025, 23:34:57 UTC**

Final delay:

**-0.23 hours**

The final delivery was slightly earlier than scheduled.

## Example 3 — Missing Intermediate Tracking

**Shipment:** SHP0238

**Route:** Singapore → Chennai → Bengaluru

**Voyage:** VG048

**Scheduled delivery:** July 31, 2025, 00:26:35 UTC

| Report available | Milestone | Stage delay | Updated ETA |
|---|---|---:|---|
| Jul 25, 06:24:33 | Departure | +0.35 h | Jul 31, 00:47:32 |
| Jul 30, 20:40:43 | Customs clearance | +5.99 h | Jul 31, 06:26:09 |

The port arrival and port-processing completion reports are missing.

The change between available observations is:

```text
Net Delay Change = 5.99 - 0.35
                 = 5.64 hours
```

The system can measure the total change across the observed interval.

It cannot reliably assign parts of the change to ocean transit, handling, or customs because those intermediate observations are unavailable.

### Final Outcome

Actual delivery:

**July 31, 2025, 03:17:19 UTC**

Final delay:

**+2.85 hours**

## Viewing the Examples

1. Open the Shipments tab.
2. Select one of the three example shipments.
3. Review the initial available ETA.
4. Advance through reported milestones.
5. Open Delay Analysis.
6. Inspect added delay, recovered time, or tracking gaps.
7. Return to shipment details.
8. Reveal the completed journey.

Actual final delivery is intentionally hidden until the completed-history view is requested.

## Example Selection

The examples were selected from recorded test shipments based on observable operational patterns:

- A large positive delay change during port processing
- A measurable recovery while the shipment was still behind schedule
- Missing intermediate reports followed by a later available report

The recorded outcomes were not modified to create these demonstrations.

The examples can be checked using:

```bash
python scripts/demonstrations.py
```
