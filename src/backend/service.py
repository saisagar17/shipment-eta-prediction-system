"""Held-out replay repository. Only an explicit historical view reads physical outcome fields."""
from functools import lru_cache
import json

import pandas as pd

from data_generation.config import HOUR, ROOT, STAGES
from data_generation.schema import DATES, PATHS
from data_generation.snapshots import EVENT_COLUMNS, features_as_of, planning_view
from ml.model import eta, load_artifacts, risk
from .forecast_models import ForecastModels
from ml.propagation import milestones


class RequestError(ValueError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


class Replay:
    def __init__(self, root=ROOT):
        self.model, schema, self.meta = load_artifacts(root)
        self.cols = schema["approved_input_columns"]
        self.forecasts = ForecastModels(root, self.cols)
        self.demonstrations = json.loads((root / "reports/demonstrations.json").read_text())
        self.comparisons = {split: self.load_comparison(root, split) for split in ("validation", "test")}

        def read(name):
            frame = pd.read_csv(root / PATHS[name], float_precision="round_trip")
            for col in DATES.intersection(frame.columns):
                frame[col] = pd.to_datetime(frame[col], utc=True)
            return frame

        manifest = read("split_manifest")
        s = read("shipments")
        s = s[
            s.shipment_id.isin(manifest.loc[manifest.split.eq("test"), "shipment_id"])
        ]
        v = read("vessel_voyages")
        self.plans = planning_view(s, v).set_index("shipment_id").to_dict("index")
        self.bookings = s.set_index("shipment_id")
        self.vessels = v.set_index("voyage_id").vessel_id.to_dict()
        self.sensors = {
            r.voyage_id: r
            for r in read("port_call_measurements").itertuples(index=False)
        }
        log = read("milestones")
        self.events = {
            sid: tuple(
                g.sort_values("stage_order")[[*EVENT_COLUMNS, "disruption_type"]].itertuples(index=False)
            )
            for sid, g in log[log.shipment_id.isin(self.plans)].groupby("shipment_id")
        }
        self.truth = (
            read("ground_truth_milestones")
            .set_index(["shipment_id", "stage_order"])
            .actual_timestamp
        )
        self.metrics = json.loads((root / "models/metrics.json").read_text())
        self.importance = json.loads((root / "models/importance.json").read_text())
        dictionary = pd.read_csv(root / "data/metadata/data_dictionary.csv")
        self.definitions = dictionary[dictionary.eligible_ml_input][
            ["column", "business_meaning", "unit"]
        ].to_dict("records")
        self.start = min(s.scheduled_departure.min(), s.actual_departure.min()).floor(
            "min"
        )
        self.end = log.loc[log.shipment_id.isin(self.plans), "event_available_at"].max().ceil("min")
        # Start the interview at a reported handling completion in the first wave.
        handling = log[log.shipment_id.isin(self.plans) & log.stage_order.eq(2)].dropna(
            subset=["event_available_at"]
        )
        self.default = (
            handling.event_available_at.sort_values()
            .iloc[len(handling) // 4]
            .ceil("min")
        )

    @staticmethod
    def load_comparison(root, split):
        folder = root / "models/tuning" / split
        scores = json.loads((folder / "metrics.json").read_text())
        names = {"E0": "Current delay", "E1": "Random Forest", "T1": "Tuned XGBoost residual",
                 "T2": "Tuned CatBoost residual"}
        rows = pd.read_csv(folder / "by_stage.csv")
        points = pd.read_csv(folder / "predictions.csv")
        return {
            "split": split, "selected": "E0", "previously_inspected_test": True, "names": names,
            "scores": {key: scores[key] for key in names},
            "stages": rows.loc[rows.candidate.isin(names)].to_dict("records"),
            "points": points[["target_final_delay_hours", *[k + "_hours" for k in names]]].to_dict("records"),
        }

    def clock(self, value):
        return (
            pd.Timestamp(value).tz_convert("UTC") if value is not None else self.default
        )

    def log(self, sid):
        if sid not in self.events:
            raise RequestError(404, "Shipment is outside the held-out demo cohort")
        return self.events[sid]

    def reported(self, sid, at):
        return [
            e
            for e in self.log(sid)
            if pd.notna(e.event_available_at) and e.event_available_at <= at
        ]

    def select(self, sid, at, stage=None):
        reports = self.reported(sid, at)
        if stage is not None:
            reports = [e for e in reports if e.stage_name == stage]
        if not reports or reports[-1].stage_order == 4:
            raise RequestError(
                422,
                "Select a reported pre-delivery stage available by the simulation clock",
            )
        return reports[-1]

    def frame(self, sid, events, sensor, at):
        features = features_as_of(self.plans[sid], events, sensor, at)
        if features is None:
            raise RequestError(422, "No active prediction at this observation time")
        return pd.DataFrame([features], columns=self.cols)

    def predict_frame(self, sid, frame, at, model_key="E0"):
        delay = self.forecasts.predict(frame, model_key)
        scheduled = self.plans[sid]["scheduled_arrival"]
        return dict(
            shipment_id=sid,
            observation_timestamp=at,
            stage=frame.snapshot_stage.iloc[0],
            scheduled_eta=scheduled,
            predicted_eta=eta(scheduled, delay),
            delay=delay,
            risk=risk(delay),
            version=self.forecasts.version if model_key == "E0" else self.meta["version"],
        )

    @lru_cache(maxsize=1024)
    def cached(self, sid, at, version):
        sensor = self.sensors[self.plans[sid]["voyage_id"]]
        frame = self.frame(sid, self.log(sid), sensor, at)
        key = "E1" if version == self.meta["version"] else "E0"
        if version not in (self.meta["version"], self.forecasts.version):
            raise ValueError("Unknown prediction version")
        return self.predict_frame(sid, frame, at, key)

    def predict(self, sid, at, stage=None):
        e = self.select(sid, at, stage)
        sensor = self.sensors[self.plans[sid]["voyage_id"]]
        frame = self.frame(sid, self.log(sid), sensor, e.event_available_at)
        values = frame.iloc[0]
        fields = [
            "current_stage_delay_hours",
            "departure_delay_hours",
            "port_arrival_delay_hours",
            "port_processing_delay_hours",
            "missing_event_count",
            "remaining_planned_hours",
            "cumulative_added_delay_hours",
            "cumulative_recovered_hours",
            "known_port_processing_hours",
            "known_customs_processing_hours",
            "observed_weather_severity",
            "observed_congestion_level",
        ]
        comparisons = self.forecasts.compare(frame)
        delay = comparisons["E0"]["delay"]
        return {
            **self.cached(sid, e.event_available_at, self.forecasts.version),
            "base_hours": 0.0,
            "contributions": [{"feature": "current_stage_delay_hours", "hours": delay}],
            "comparisons": {
                key: {**value, "predicted_eta": eta(self.plans[sid]["scheduled_arrival"], value["delay"])}
                for key, value in comparisons.items()
            },
            "reported_conditions": {report.stage_name: report.disruption_type
                for report in self.reported(sid, e.event_available_at)
                if report.stage_order < 4 and pd.notna(report.disruption_type)},
            "observed": {
                c: float(values[c]) if pd.notna(values[c]) else None for c in fields
            },
            "summary": f"Latest reported milestone was {values.current_stage_delay_hours:+.1f} hours from schedule.",
        }

    def row(self, sid, at):
        reports = self.reported(sid, at)
        s = self.bookings.loc[sid]
        stage = reports[-1].stage_name if reports else "not_started"
        status = (
            "Delivered"
            if stage == STAGES[4]
            else "In transit"
            if reports
            else "Awaiting departure"
        )
        pred = (
            self.cached(sid, reports[-1].event_available_at, self.forecasts.version)
            if status == "In transit"
            else None
        )
        reasons = []
        if pred:
            if pred["delay"] > 2:
                reasons.append(f"Forecast is {pred['delay']:.1f} h behind schedule.")
            skipped = reports[-1].stage_order + 1 - len(reports)
            if skipped:
                reasons.append(f"{skipped} intermediate report{'s' if skipped != 1 else ''} missing.")
            if len(reports) > 1:
                a, b = reports[-2:]
                delta = ((b.actual_timestamp - b.scheduled_timestamp)
                         - (a.actual_timestamp - a.scheduled_timestamp)) / HOUR
                if delta > 0:
                    if b.stage_order > a.stage_order + 1:
                        reasons.append(f"Observed deviation grew by {delta:.1f} h across the reporting gap.")
                    else:
                        stage_label = b.stage_name.replace("_complete", "").replace("_", " ").capitalize()
                        reasons.append(f"{stage_label} increased observed deviation by {delta:.1f} h.")
        return dict(
            attention_reasons=reasons,
            shipment_id=sid,
            voyage_id=s.voyage_id,
            route_id=s.route_id,
            route=f"{s.origin} → {s.destination_port} → {s.final_destination}",
            vessel=self.vessels[s.voyage_id],
            cargo=s.cargo_type,
            scheduled_eta=s.scheduled_arrival,
            stage=stage,
            status=status,
            prediction=pred,
        )

    def detail(self, sid, at, historical):
        row = self.row(sid, at)
        if historical:
            at = self.end
            row = self.row(sid, at)
        truth = self.truth.loc[sid].to_dict() if historical else None
        return {
            **row,
            "as_of": at,
            "historical": historical,
            "actual_delivery": truth[4] if historical else None,
            "milestones": milestones(self.log(sid), at, truth),
        }

    def propagation(self, sid, at):
        updates = []
        previous = None
        for e in self.reported(sid, at):
            if e.stage_order == 4:
                continue
            p = self.cached(sid, e.event_available_at, self.forecasts.version)
            updates.append(
                {
                    **p,
                    "change_from_previous": None
                    if previous is None
                    else p["delay"] - previous,
                }
            )
            previous = p["delay"]
        return {"milestones": milestones(self.log(sid), at), "updates": updates}

    def advance(self, sid, at):
        next_reports = [e.event_available_at for e in self.log(sid)
                        if pd.notna(e.event_available_at) and at < e.event_available_at and e.stage_order < 4]
        if not next_reports:
            raise RequestError(422, "No later pre-delivery report. Reveal completed history to inspect delivery.")
        return {"as_of": min(next_reports)}

    def scenario(self, sid, at, stage, hours):
        e = self.select(sid, at, stage)
        if e.stage_order >= 3:
            raise RequestError(
                422,
                "Final delivery is the target. Choose departure, arrival or port processing.",
            )
        at = e.event_available_at
        future = self.log(sid)[e.stage_order + 1]
        booked = (future.scheduled_timestamp - e.scheduled_timestamp) / HOUR
        if not 0.25 <= hours <= booked * 2.5:
            raise RequestError(
                422, f"Duration must lie between 0.25 and {booked*2.5:.2f} hours"
            )
        visible = self.reported(sid, at)
        sensor = self.sensors[self.plans[sid]["voyage_id"]]
        # Freeze current measurements. Neither branch reads future sensor values or physical events.
        sensor = sensor._replace(
            weather_available_at=sensor.weather_available_at
            if sensor.weather_available_at <= at
            else pd.NaT,
            congestion_available_at=sensor.congestion_available_at
            if sensor.congestion_available_at <= at
            else pd.NaT,
        )

        def branch(duration):
            physical = e.actual_timestamp + pd.Timedelta(hours=duration)
            release = max(at, physical)
            hypothetical = future._replace(
                actual_timestamp=physical, event_available_at=release
            )
            return self.predict_frame(
                sid, self.frame(sid, [*visible, hypothetical], sensor, release), release
            )

        base, alternative = branch(booked), branch(hours)
        return dict(
            hypothetical=True,
            stage=future.stage_name,
            baseline_hours=booked,
            expected_hours=hours,
            baseline=base,
            scenario=alternative,
            change_delay=alternative["delay"] - base["delay"],
            change_eta_hours=(alternative["predicted_eta"] - base["predicted_eta"])
            / HOUR,
        )

    def metadata(self):
        return dict(
            routes=self.bookings[
                ["route_id", "origin", "destination_port", "final_destination"]
            ]
            .drop_duplicates()
            .sort_values("route_id")
            .to_dict("records"),
            cargo=sorted(self.bookings.cargo_type.unique()),
            vessels=sorted(set(self.vessels.values())),
            stages=STAGES,
            start=self.start,
            end=self.end,
            default_time=self.default,
            version=self.forecasts.version,
            demonstrations=self.demonstrations,
            modes=["operational", "historical"],
            cohort="Held-out test voyages",
            shipments=sorted(self.plans),
        )

    def dashboard(self, at):
        rows = [self.row(s, at) for s in self.plans]
        active = [r for r in rows if r["prediction"]]

        def count(key, value):
            return sum(r[key] == value for r in active)

        risks = {
            band: sum(r["prediction"]["risk"] == band for r in active)
            for band in ["Low", "Moderate", "High"]
        }
        trend = {}
        for sid in self.plans:
            for e in self.reported(sid, at):
                if e.stage_order < 4 and e.event_available_at >= at - pd.Timedelta(
                    days=7
                ):
                    key = e.event_available_at.strftime("%Y-%m-%d")
                    pred = self.cached(sid, e.event_available_at, self.forecasts.version)
                    trend.setdefault(key, []).append(
                        (
                            pred["delay"],
                            (e.actual_timestamp - e.scheduled_timestamp) / HOUR,
                        )
                    )
        daily = [
            dict(
                date=k,
                predicted=sum(x for x, y in pairs) / len(pairs),
                observed=sum(y for x, y in pairs) / len(pairs),
                n=len(pairs),
            )
            for k, pairs in sorted(trend.items())
        ]
        delays = [r["prediction"]["delay"] for r in active]
        return dict(
            total=len(rows),
            active=len(active),
            risks=risks,
            average=sum(delays) / len(delays) if delays else None,
            stages={k: count("stage", k) for k in STAGES[:4]},
            trend=daily,
            on_time=sum(x <= 0 for x in delays) / len(delays) if delays else None,
            delivered=sum(r["status"] == "Delivered" for r in rows),
            attention=sorted(
                [r for r in active if r["attention_reasons"]],
                key=lambda r: -r["prediction"]["delay"],
            )[:6],
        )
