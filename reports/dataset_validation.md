# Synthetic Shipment Dataset — Design and Validation

## Dataset Overview

The shipment dataset represents cargo movement across maritime and inland logistics operations.

It contains planned shipment schedules, realized operational events, tracking reports, and environmental measurements.

The purpose of the dataset is to study ETA prediction and the way delays accumulate or recover between stages.

All timestamps use UTC.

## Dataset Summary

| Dataset | Records |
|---|---:|
| Vessel voyages | 50 |
| Shipments | 250 |
| Ground-truth milestones | 1,250 |
| Milestone records | 1,250 |
| Port-call measurements | 50 |
| Prediction snapshots | 927 |
| Split manifest | 250 |

The dataset contains five routes and ten vessels.

Each route uses two vessels. Individual vessels can perform multiple voyages, with sufficient time between consecutive voyages.

Voyages carry between four and six shipments.

## Shipment Routes

| Route | Journey | Shipments |
|---|---|---:|
| R01 | Chennai → Mumbai → Pune | 55 |
| R02 | Singapore → Chennai → Bengaluru | 47 |
| R03 | Kochi → Mumbai → Nashik | 50 |
| R04 | Dubai → Mumbai → Pune | 51 |
| R05 | Colombo → Chennai → Hyderabad | 47 |

Routes have different planned transit times, handling requirements, and weather sensitivity.

## Shipment Milestones

Each shipment follows five stages:

1. Origin departure
2. Destination port arrival
3. Port processing completion
4. Customs clearance completion
5. Final delivery

Planned timestamps are generated before actual operational disruptions.

Actual events are generated in chronological order, preserving physically consistent journeys.

## Operational Delay Generation

### Departure

Departure reliability includes routine, moderate, and severe disruptions.

The simulation assigns these cases probabilities of 70%, 20%, and 10%.

Departure deviations can be negative or positive.

### Ocean Transit

Sailing duration depends on:

- Route distance and planned sailing duration
- Weather severity
- Random operational variation

Shipments sharing one voyage experience the same maritime conditions.

### Port Processing

Port handling includes waiting, unloading, and cargo-related processing.

Congestion increases processing duration through a nonlinear relationship.

Different cargo categories can have different handling requirements.

### Customs Clearance

Customs processing includes documentation effort, workload variation, and possible inspection delays.

The simulation uses a 14% inspection probability.

Inspections can add four to fourteen hours.

### Inland Delivery

Inland transportation includes travel-time variation and possible missed dispatch windows.

Some delay may be recovered through faster operations.

Missed dispatch windows can introduce additional delays.

## Ground Truth

Final delay is measured as:

```text
Final Delay =
    Actual Final Delivery - Scheduled Final Delivery
```

Positive values indicate late arrival.

Negative values indicate early arrival.

At every stage:

```text
Stage Deviation =
    Actual Milestone Time - Scheduled Milestone Time
```

The difference between consecutive stage deviations represents net delay added or recovered.

The complete physical milestone history is stored separately from observable tracking reports.

## Final Delay Distribution

| Statistic | Hours |
|---|---:|
| Minimum | -12.09 |
| 25th percentile | -1.34 |
| Median | 1.69 |
| Mean | 3.62 |
| 75th percentile | 6.32 |
| 90th percentile | 14.82 |
| Maximum | 32.02 |
| Standard deviation | 7.28 |

### Delivery Outcome Distribution

| Outcome | Shipments |
|---|---:|
| More than two hours early | 48 |
| Within ±2 hours | 87 |
| More than 2 and up to 6 hours late | 48 |
| More than 6 hours late | 67 |

There are 89 shipments with negative final delay.

The dataset contains both delay amplification and recovery cases.

- 178 shipments experience at least one partial recovery while still late.
- 181 shipments experience at least one increase in an existing positive delay.
- 116 shipments have net recovery from departure to delivery.
- 134 shipments have net amplification from departure to delivery.

These measurements use the complete physical event history.

## Congestion and Weather Relationships

Weather and congestion are modeled as operational variables.

Across 50 port calls:

| Relationship | Pearson correlation |
|---|---:|
| Weather severity versus excess sailing time | 0.555 |
| Congestion versus average cargo handling duration | 0.908 |

These relationships reflect the synthetic simulation rules.

They should not be interpreted as measured relationships in real ports.

## Missing Observations

Intermediate tracking and sensor reports may be absent.

| Observation | Missing | Approximate rate |
|---|---:|---:|
| Intermediate tracking slots | 73 / 750 | 9.73% |
| Port arrival shipment slots | 23 / 250 | 9.20% |
| Processing completion reports | 25 / 250 | 10.00% |
| Customs completion reports | 25 / 250 | 10.00% |
| Weather reports | 3 / 50 | 6.00% |
| Congestion reports | 5 / 50 | 10.00% |
| Departure and final delivery | 0 | 0% |

Missing observations do not remove the complete ground-truth events.

The system distinguishes the physical journey from the information available to a prediction.

## Prediction Snapshots

Snapshots are created when reported pre-delivery milestones become available.

| Prediction stage | Snapshots |
|---|---:|
| Departure | 250 |
| Port arrival | 227 |
| Port processing | 225 |
| Customs clearance | 225 |
| Total | 927 |

Every snapshot contains features representing the information known at that observation time.

Future tracking reports and unreleased sensor measurements are excluded.

The final delivery outcome is attached as a training or evaluation target after feature construction.

## Chronological Data Splitting

The data is divided using chronological vessel groups.

| Partition | Shipments | Voyages | Snapshots |
|---|---:|---:|---:|
| Training | 175 | 35 | 665 |
| Validation | 25 | 5 | 87 |
| Test | 50 | 10 | 175 |

Shipments from the same voyage remain in the same partition.

All snapshots from a shipment also remain together.

Training labels must be available before the subsequent evaluation period begins.

The recorded gap before validation is approximately 273 hours.

The gap before the test period is approximately 223 hours.

## Data Integrity

The validation checks cover:

- Unique shipment, voyage and snapshot identifiers
- Valid foreign-key relationships
- Shared vessel timing consistency
- Chronological milestone ordering
- Non-overlapping vessel schedules
- Correct final-delay calculation
- Stage-level delay reconciliation
- Missing observation rules
- Event and sensor release times
- Prediction feature availability
- Voyage-grouped partition integrity
- Chronological label-availability boundaries
- Reproducible generation from the configured seed

The dataset reference validation recorded 25 passing automated tests.

## Reproducibility

The data-generation configuration uses seed 42.

To inspect the existing dataset:

```bash
python scripts/validate_dataset.py
```

To regenerate data for a separate experiment:

```bash
python scripts/generate_dataset.py
```

Regeneration is not required to run the supplied application and may overwrite the existing synthetic records.

For regular application use, retain the included dataset and saved model artifacts.

## Limitations

This dataset represents simulated logistics behavior.

It does not contain historical carrier records or measured real-world delivery outcomes.

The simulation simplifies seasonal changes, port resource constraints, vessel repositioning, and correlated disruptions.

The limited number of independent voyages also restricts how confidently model results can be generalized.
