# Shipment ETA synthetic dataset validation

## Scope and design

This completed-history cohort supports supervised prediction of inland delivery time and signed delay at successive tracking reports. All timings, operating rules and probabilities are scenario assumptions. Seed 42 drives separate schedule, voyage, cargo and observation streams. The scheduler builds every planned timestamp before drawing realized disruptions. UTC clocks are rounded to the nearest second.

| Table | Rows |
| --- | --- |
| vessel_voyages | 50 |
| shipments | 250 |
| ground_truth_milestones | 1250 |
| milestones | 1250 |
| port_call_measurements | 50 |
| prediction_snapshots | 927 |
| split_manifest | 250 |

The fleet has 10 vessels. Each route rotates a roster of 2 ships in waves spaced 22 days apart. Randomized sailing order within a wave gives one voyage per day for five days. The scheduler assigns the vessel before drawing departure reliability, weather and congestion for the port call. All cargo on that voyage shares its sailing clocks and call conditions. Unrecorded empty return and turnaround use an allowance of one nominal ocean duration plus 24 hours before reuse. Minimum observed idle interval across 40 vessel reuses is 803.32 hours. The voyage-size distribution is 20 voyages with 4 shipments, 10 voyages with 5 shipments, 20 voyages with 6 shipments.

## Routes and schedule assumptions

| Route | Journey | Planned sea range (h) | Weather scale (h) | Vessels | Shipments | Actual total min (h) | Median (h) | Max (h) | Early/on time | Significant |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R01 | Chennai → Mumbai → Pune | 66.96–77.04 | 6 | 2 | 55 | 85.45 | 95.06 | 112.19 | 22 | 15 |
| R02 | Singapore → Chennai → Bengaluru | 111.60–128.40 | 9 | 2 | 47 | 133.29 | 152.07 | 174.55 | 16 | 20 |
| R03 | Kochi → Mumbai → Nashik | 44.64–51.36 | 5 | 2 | 50 | 62.02 | 72.13 | 89.52 | 12 | 14 |
| R04 | Dubai → Mumbai → Pune | 156.24–179.76 | 12 | 2 | 51 | 178.45 | 196.53 | 213.00 | 18 | 12 |
| R05 | Colombo → Chennai → Hyderabad | 44.64–51.36 | 4 | 2 | 47 | 66.70 | 77.41 | 93.67 | 21 | 6 |

Ocean allowances vary uniformly within the stated range. Handling, customs and road baselines vary ±10% around route-specific values. Cargo handling and documentation increments enter the first two baselines before booking. Planned allowances then include 2 h of handling slack, 1.5 h of customs slack and 1.5 h of road slack. Route baselines and cargo increments are recorded in `dataset_config.json`.

## Physical stages and delay mechanisms

The earlier design allowed 8.5 h of downstream slack on every booking. This version allows 5 h across three stages. Handling retains the largest buffer because it includes queues and unloading. Customs and road retain smaller allowances for routine variability. Inspections and missed windows can exceed those allowances. Changes enter the booked schedule before sailing and can affect later dispatch decisions. The same scenario probabilities govern every vessel.

1. Vessel departure uses routine, moderate and severe cases with probabilities 70%, 20%, 10%. Uniform deviations span −1 to +2, +2 to +8 and +8 to +18 hours respectively.
2. Ocean duration adds route scale × weather severity^1.5 and normal sailing variation (mean −1.8 h, SD 1.8 h) to the booking. Severity follows Beta(1.5, 2). Every consignment on the voyage shares this realization.
3. Port handling includes waiting and unloading. Route and cargo effort are increased by 2c + 9c² hours for shared congestion c ~ Beta(1.7, 1.9), plus normal variation (mean −0.8 h, SD 1.3 h).
4. Customs adds gamma-distributed documentation effort, uniform workload variation and normal noise to route and cargo effort. An independent inspection with probability 14% adds 4–14 hours. There were 48 inspections.
5. Inland duration uses the booked destination-specific road baseline before slack, plus traffic noise. Late releases can shorten dispatch by 20% of lateness up to the road buffer. Releases over 3 h late miss their next window with probability 30%, compared with 6% otherwise. A missed window adds 3–10 h. Each realized interval has a 1 h physical floor.

Signed deviation at a stage equals actual time minus booked time. Over each physical interval the change equals actual duration minus planned duration. Positive changes add delay and negative changes recover it. The initial deviation plus subsequent additions minus recoveries reconstructs final delay. The maximum absolute reconciliation residual after CSV serialization was 2.00e-12 h.

## Distribution checks

| Milestone | Min | P25 | Median | Mean | P75 | P90 | Max | SD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Final delivery | -12.09 | -1.34 | 1.69 | 3.62 | 6.32 | 14.82 | 32.02 | 7.28 |
| origin_departure | -0.89 | -0.13 | 0.95 | 1.62 | 1.85 | 3.56 | 15.47 | 3.25 |
| port_arrival | -5.27 | -0.29 | 1.67 | 2.04 | 3.47 | 4.49 | 16.81 | 4.24 |
| port_processing_complete | -7.44 | 0.48 | 2.47 | 3.35 | 4.57 | 7.08 | 22.16 | 5.07 |
| customs_clearance_complete | -9.89 | -0.45 | 2.42 | 3.96 | 6.30 | 14.82 | 26.40 | 6.62 |

All values above are signed schedule deviations in hours. SD is the sample standard deviation. Outcomes below count shipments once.

| Exclusive delivery band | Shipments |
| --- | --- |
| More than 2 h early | 48/250 (19.2%) |
| Within ±2 h, endpoints included | 87/250 (34.8%) |
| Moderate (over 2 through 6 h late) | 48/250 (19.2%) |
| Significant (over 6 h late) | 67/250 (26.8%) |

| Shipment outcome (categories may overlap) | Shipments |
| --- | --- |
| Early (signed delay < 0 h) | 89/250 (35.6%) |
| Near schedule (absolute delay ≤ 2 h) | 87/250 (34.8%) |
| Significantly delayed (> 6 h) | 67/250 (26.8%) |
| At or below significant threshold | 183/250 (73.2%) |
| At least one partial recovery while still late | 178/250 (71.2%) |
| At least one increase in an existing positive delay | 181/250 (72.4%) |
| Net recovery from departure to delivery | 116/250 (46.4%) |
| Net amplification from departure to delivery | 134/250 (53.6%) |
| At least one shorter-than-planned interval | 237/250 (94.8%) |
| At least one longer-than-planned interval | 241/250 (96.4%) |

The voyage simulator drew 2 severe departure disruptions (8–18 h). Propagation frequencies above use the complete physical ledger, including stages absent from tracking.

Across 50 port calls, the Pearson correlation between weather and sailing time above the route-specific booking was 0.555. The correlation between congestion and mean cargo handling duration per call was 0.908. Each voyage contributes one observation to each calculation.

| Driver / outcome | Calls per tail | Lowest severity mean (h) | Highest severity mean (h) |
| --- | --- | --- | --- |
| Weather / excess sailing | 12 | -1.37 | 2.73 |
| Congestion / mean handling | 12 | 8.64 | 14.10 |

## Observation masks and feature availability

Sample missing reports and sensors uniformly without replacement in their eligible populations. Round requested numbers to the nearest whole report (half up). Port-arrival reports, their release times and both sensor messages are shared at voyage level. Handling and customs reports have shipment-specific masks. The weather and congestion sensors have independent masks and release clocks 5–60 minutes after physical port arrival. Their measurements may arrive even when the tracking message is missing.

| Unit | Eligible | Missing | Rate |
| --- | --- | --- | --- |
| Intermediate tracking slots | 750 | 73 | 9.73% |
| Shared port-arrival messages | 50 | 5 | 10.00% |
| Port arrival, shipment slots | 250 | 23 | 9.20% |
| Handling completion messages | 250 | 25 | 10.00% |
| Customs completion messages | 250 | 25 | 10.00% |
| Weather sensors, port calls | 50 | 3 | 6.00% |
| Congestion sensors, port calls | 50 | 5 | 10.00% |
| Departure or delivery slots | 500 | 0 | 0.00% |
| Historical final-delay labels | 250 | 0 | 0.00% |

| Triggering report | Snapshots |
| --- | --- |
| origin_departure | 250 |
| port_arrival | 227 |
| port_processing_complete | 225 |
| customs_clearance_complete | 225 |

Each observed milestone summary can mirror a sensor value on a reported arrival row. Use the matching sensor release clock from `port_call_measurements.csv` for as-of reads. Tracking lag is 0–20 minutes, with immediate final delivery confirmation. A missing tracking event retains its booked slot and loses its occurrence time, report time, reason and deviation. Processing begins at the previous boundary and its interval is available only when both boundary reports exist. Fields outside their applicable stages are blank.

Snapshots use a planning projection, time-filtered event messages and independent sensor releases. At departure, future events and unreleased sensors stay blank. The count of missing events includes only gaps preceding the highest observed stage. Pending and permanently missing reports are indistinguishable at that cutoff. The archived flag `event_missing` is retrospective. Across a tracking gap, cumulative changes capture only the visible net difference. At a report trigger, event age is time since physical occurrence, so it can equal the report lag. Labels are attached after feature construction from completed shipment records. A later status service can reconstruct live progress from the latest available report.

## Shared voyage example

Voyage VG001 on vessel V04 carried the two consignments below. The example uses the physical ledger, including any event absent from tracking.

| Physical stage | SHP0001 UTC | Deviation (h) | SHP0002 UTC | Deviation (h) |
| --- | --- | --- | --- | --- |
| origin_departure | 2025-01-06 05:08:22 | -0.86 | 2025-01-06 05:08:22 | -0.86 |
| port_arrival | 2025-01-12 20:14:39 | -5.27 | 2025-01-12 20:14:39 | -5.27 |
| port_processing_complete | 2025-01-13 06:16:15 | -5.47 | 2025-01-13 10:59:18 | -2.58 |
| customs_clearance_complete | 2025-01-13 11:41:56 | -6.87 | 2025-01-13 17:47:22 | -4.61 |
| final_delivery | 2025-01-13 15:50:23 | -8.81 | 2025-01-13 23:13:57 | -5.73 |

| Shipment | Cargo | Handling (h) | Customs (h) | Road (h) | Final delay (h) |
| --- | --- | --- | --- | --- | --- |
| SHP0001 | general_goods | 10.03 | 5.43 | 4.14 | -8.81 |
| SHP0002 | industrial_equipment | 14.74 | 6.80 | 5.44 | -5.73 |

## Partitions and integrity checks

Sort voyages by scheduled departure and voyage ID. For each possible cut, compare the latest final-delivery report of **all** earlier consignments with the earliest scheduled or physical departure among **all** later voyages. A cut is eligible only if the report strictly precedes that departure. Among eligible pairs, minimize the sum of absolute distances from the cumulative 70% and 85% shipment targets. Equal costs select the earlier pair in voyage order. All voyages are retained. No delay magnitude, class label or route outcome statistic participates in selecting a boundary.

| Partition | Shipments | Voyages | Snapshots | First booked sailing (UTC) | Last booked sailing (UTC) | Significant | At or below threshold |
| --- | --- | --- | --- | --- | --- | --- | --- |
| train | 175 | 35 | 665 | 2025-01-06 | 2025-05-22 | 46/175 (26.3%) | 129 |
| validation | 25 | 5 | 87 | 2025-06-09 | 2025-06-13 | 11/25 (44.0%) | 14 |
| test | 50 | 10 | 175 | 2025-07-01 | 2025-07-27 | 10/50 (20.0%) | 40 |

| Evaluation period | Latest earlier label (UTC) | Earliest later start (UTC) | Gap (h) |
| --- | --- | --- | --- |
| Validation | 2025-05-28T20:59:33+00:00 | 2025-06-09T06:00:00+00:00 | 273.01 |
| Test | 2025-06-21T23:14:13+00:00 | 2025-07-01T06:00:00+00:00 | 222.76 |

The on-disk audit passed the following checks for this run.

- Keys, schemas and route references
- Shared vessel movements and return allowance
- Strictly ordered planned and physical timelines
- Physical interval and signed-delay reconciliation
- Observation masks, reporting clocks and sensor applicability
- All snapshot triggers, features and labels
- Route roster rotation and disjoint voyage groups
- All earlier delivery reports released before each evaluation cutoff

The audit independently reconstructs each as-of feature from persisted tracking and sensor clocks. Tests move individual release times, alter future outcomes across a route, exercise early evaluation departures, and compare generated file bytes.

## Recorded automated test results

The recorded repository reference run collected 25 tests. 25 passed, 0 failed, 0 errored and 0 skipped. Counts come from the archived pytest JUnit results for the seed-42 reference cohort.

## Limits of interpretation

The synthetic durations, thresholds, distributions and masks lack carrier calibration. Routes have dedicated vessel pools, and cargo on a shared voyage experiences correlated maritime conditions. The partition table shows the small numbers of independent voyage groups and significantly late consignments available for evaluation. Multiple snapshots from a single late shipment carry the same label. The simulation omits seasonal and inter-port dependencies, detailed repositioning, resource queues and correlated outages.
