# Shipment ETA Prediction System — Quick Walkthrough

This guide demonstrates how the application predicts final delivery times and explains changes in shipment delays.

The examples use three shipments from the saved test dataset. All displayed timestamps are in UTC.

## Start the Application

Follow the instructions in [README.md](README.md) to start the backend and frontend.

Open:

http://127.0.0.1:5236/dashboard

## 1. Explore the Dashboard

The Dashboard displays the shipment overview, active deliveries, predicted delays, delay categories, and shipments requiring attention.

Use the simulation timestamp to view the information available at different moments in the shipment journey.

Select a shipment to open its details.

## 2. Delay Amplification — SHP0218

Open **Shipments** and choose **Delay amplification · SHP0218**.

This shipment travels from Chennai through Mumbai to Pune.

Advance through the available tracking reports.

| Milestone | Observed delay |
|---|---:|
| Departure | +0.35 h |
| Port arrival | +0.56 h |
| Port processing | +6.73 h |

The increase from port arrival to processing is:

```text
6.73 - 0.56 = 6.17 hours
```

The operational ETA moves from July 8, 02:50 UTC to July 8, 09:00 UTC.

Open **Delay Analysis** to inspect the increase in schedule deviation.

## 3. Delay Recovery — SHP0236

Choose **Partial delay recovery · SHP0236**.

This shipment travels from Singapore through Chennai to Bengaluru.

At port processing, the observed deviation is +3.56 hours.

After customs clearance, it decreases to +0.74 hours.

```text
Recovered time = 3.56 - 0.74
               = 2.82 hours
```

The updated ETA moves earlier because the later operation recovered some of the accumulated delay.

The shipment remains slightly behind schedule.

## 4. Missing Tracking — SHP0238

Choose **Missing intermediate tracking · SHP0238**.

The departure report shows a deviation of +0.35 hours.

The next available report is customs clearance, with a deviation of +5.99 hours.

Two intermediate reports are missing.

The observable change is:

```text
5.99 - 0.35 = 5.64 hours
```

This change belongs to the complete interval between the two reported events.

The system does not assign an unsupported portion of the delay to an individual missing stage.

## 5. Understand the Forecast

Open the **Why This ETA?** section on the shipment details page.

Review:

- Current known schedule deviation
- Observed additional delay
- Recovered time
- Available operational measurements
- Prediction method
- Model-based explanations

The operational forecast uses the latest known deviation.

The other models estimate the remaining delay change using available shipment features.

## 6. Reveal the Completed Journey

After reviewing the available forecasts, select **Reveal completed history**.

Compare the latest prediction with the actual final delivery time.

Returning to replay hides future information again.

## 7. Compare Prediction Methods

Open **Model Performance**.

Compare validation and test metrics for persistence, Random Forest, XGBoost, and CatBoost.

Persistence has the lowest overall validation and test MAE, while some learned models have lower squared-error or severe-delay underprediction measures.

## Further Reading

The [detailed demonstration guide](reports/demonstration_guide.md) contains exact report timestamps and the final delivery outcomes for all three shipments.
