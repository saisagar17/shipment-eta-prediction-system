import { useState } from "react";
import { Link } from "react-router-dom";
import { CalendarClock, Check, Clock3, Hourglass, Route } from "lucide-react";
import { qs, request, useApi } from "./api";
import {
  Badge,
  fmt,
  Heading,
  hrs,
  label,
  Panel,
  Pairs,
  Stats,
  Trend,
  useClock,
  Wait,
  yellow,
  slate,
} from "./ui";
import type {
  Detail,
  Estimate,
  Journey,
  Milestone,
  Page,
  Scenario,
} from "./types";

import { Interactions } from "./Interactions";
import { ForecastEvidence, Revisions } from "./ForecastEvidence";
import { PropagationCharts } from "./PropagationCharts";

function Timeline({ rows }: { rows: Milestone[] }) {
  return (
    <ol className="timeline">
      {rows.map((m) => (
        <li key={m.stage} className={m.state === "reported" ? "done" : ""}>
          <span>
            {m.state === "reported" ? (
              <Check size={14} />
            ) : m.state.includes("gap") || m.state === "unreported" ? (
              "?"
            ) : (
              ""
            )}
          </span>
          <b>{label(m.stage)}</b>
          <small>{m.actual ? fmt(m.actual) : label(m.state)}</small>
          {m.state === "unreported" && <small>Unreported</small>}
        </li>
      ))}
    </ol>
  );
}
function ScenarioPanel({
  sid,
  at,
  stage,
  rows,
}: {
  sid: string;
  at: string;
  stage: string;
  rows: Milestone[];
}) {
  const i = rows.findIndex((r) => r.stage === stage),
    next = rows[i + 1];
  const booked = next
    ? (Date.parse(next.scheduled) - Date.parse(rows[i].scheduled)) / 3600000
    : 0;
  const [value, setValue] = useState((booked + 2).toFixed(2)),
    [result, setResult] = useState<Scenario>(),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setResult(undefined);
    setError("");
    try {
      setResult(
        await request<Scenario>(
          "/scenario",
          undefined,
          JSON.stringify({
            shipment_id: sid,
            as_of: at,
            stage,
            expected_hours: Number(value),
          }),
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title="What-If Scenario">
      {i >= 3 ? (
        <p className="muted">
          Choose departure, port arrival, or port processing to explore the next
          interval.
        </p>
      ) : (
        <>
          <p className="muted">
            Compare two hypothetical {label(next.stage).toLowerCase()} reports.
            The baseline uses the booked {booked.toFixed(1)}-hour interval.
          </p>
          <form className="controls" onSubmit={submit}>
            <label>
              Expected next interval (hours)
              <input
                className="interval-slider"
                aria-label="Adjust expected duration"
                type="range"
                min=".25"
                step=".01"
                max={(booked * 2.5).toFixed(2)}
                value={value}
                onChange={(e) => {
                  setValue(e.target.value);
                  setResult(undefined);
                }}
              />
              <input
                aria-label="Expected next interval"
                type="number"
                step="0.01"
                min=".25"
                max={(booked * 2.5).toFixed(2)}
                required
                value={value}
                onChange={(e) => {
                  setValue(e.target.value);
                  setResult(undefined);
                }}
              />
            </label>
            <button className="primary" disabled={busy}>
              {busy ? "Calculating…" : "Compare ETAs"}
            </button>
          </form>
          {error && <p role="alert">{error}</p>}
          {result && (
            <Pairs
              rows={[
                ["Booked-interval ETA", fmt(result.baseline.predicted_eta)],
                ["Scenario ETA", fmt(result.scenario.predicted_eta)],
                ["Hypothetical delay change", hrs(result.change_delay)],
              ]}
            />
          )}
        </>
      )}
    </Panel>
  );
}

export function JourneyView({
  sid,
  analysis = false,
}: {
  sid: string;
  analysis?: boolean;
}) {
  const { at, setAt } = useClock(),
    [advanceError, setAdvanceError] = useState(""),
    [advancing, setAdvancing] = useState(false),
    [selected, setSelected] = useState(() => {
      const query = new URLSearchParams(location.search);
      return query.get("clock") === at ? query.get("stage") ?? "" : "";
    }),
    [historical, setHistorical] = useState(false);
  const detail = useApi<Detail>(
      "/shipments/" +
        sid +
        "?" +
        qs({ as_of: at, historical: String(historical) }),
    ),
    d = detail.data;
  const allowed = (d?.milestones ?? []).filter(
    (m) => m.released && m.order < 4,
  );
  const chosen =
    allowed.find((m) => m.stage === selected) ?? allowed[allowed.length - 1];
  const cutoff = chosen?.released;
  const journey = useApi<Journey>(
    cutoff && !historical
      ? "/shipments/" + sid + "/propagation?" + qs({ as_of: cutoff })
      : null,
  );
  const estimate = useApi<Estimate>(
    cutoff && !historical ? "/predict" : null,
    cutoff
      ? JSON.stringify({ shipment_id: sid, as_of: cutoff, stage: chosen.stage })
      : undefined,
  );
  async function advance() {
    setAdvancing(true);
    setAdvanceError("");
    try {
      const result = await request<{as_of: string}>("/shipments/"+sid+"/advance?"+qs({as_of: cutoff || at}), undefined, "{}");
      setSelected("");
      setAt(result.as_of);
    } catch (error) {
      setAdvanceError((error as Error).message);
    } finally {
      setAdvancing(false);
    }
  }
  if (!d) return <Wait {...detail} />;
  const pred = estimate.data,
    j = journey.data;
  return (
    <article className={analysis ? "journey analysis" : "journey"}>
      <div className="panel">
        <div className="detailhead">
          <div>
            <h2>
              {sid} {pred && !historical && <Badge risk={pred.risk} />}
            </h2>
            <p>{d.route} · {historical ? "Completed journey" : chosen ? label(chosen.stage) + " report" : d.status}</p>
          </div>
          {
            <button
              aria-pressed={historical}
              onClick={() => {
                setHistorical(!historical);
                setSelected("");
              }}
            >
              {historical ? "Return to replay" : "Reveal completed history"}
            </button>
          }
        </div>
        {historical ? (
          <>
            <h3>Historical completed journey</h3>
            <p>Actual final delivery · {fmt(d.actual_delivery)} UTC</p>
            <Timeline rows={d.milestones} />
            <p className="muted">Physical ledger after reveal. Unreported stages were unavailable to the forecaster.</p>
            <Revisions rows={d.milestones} updates={[]} completed />
          </>
        ) : (
          <>
            <div className="controls">
              <label>
                Reported prediction stage
                <select
                  aria-label="Reported prediction stage"
                  value={chosen?.stage ?? ""}
                  onChange={(e) => setSelected(e.target.value)}
                >
                  {!allowed.length && <option value="">No reports yet</option>}
                  {allowed.map((e) => (
                    <option value={e.stage} key={e.stage}>
                      {label(e.stage)}
                    </option>
                  ))}
                </select>
              </label>
              <button type="button" disabled={advancing || chosen?.order === 3} onClick={advance}>
                {advancing ? "Advancing…" : "Advance to next report"}
              </button>
              <span className="muted">
                {chosen ? "Replay as of " + fmt(cutoff) + " UTC" : d.status}
              </span>
            </div>
            {advanceError && <p role="alert">{advanceError}</p>}
            {!chosen ? (
              <p className="empty">
                The first departure report is pending at this simulation time.
              </p>
            ) : !j || !pred ? (
              <Wait {...(!j ? journey : estimate)} />
            ) : (
              <>
                <Stats
                  items={[
                    {
                      icon: CalendarClock,
                      title: analysis
                        ? "Observed stage delay"
                        : "Scheduled delivery",
                      value: analysis
                        ? hrs(pred.observed.current_stage_delay_hours)
                        : fmt(d.scheduled_eta),
                    },
                    {
                      icon: Clock3,
                      title: "Predicted delivery · UTC",
                      value: fmt(pred.predicted_eta),
                    },
                    {
                      icon: Hourglass,
                      title: "Predicted delay",
                      value: hrs(pred.delay),
                    },
                    {
                      icon: Route,
                      title: analysis ? "Remaining planned time" : "Delay risk",
                      value: analysis
                        ? hrs(pred.observed.remaining_planned_hours)
                        : pred.risk,
                    },
                  ]}
                />
                {!analysis && (
                  <>
                    <h3>Shipment Progress</h3>
                    <Timeline rows={j.milestones} />
                  </>
                )}
              </>
            )}
          </>
        )}
      </div>
      {!historical && chosen && j && pred && (
        <>
          {analysis ? (
            <><PropagationCharts rows={j.milestones} /><Revisions rows={j.milestones} updates={j.updates} /></>
          ) : (
            <div className="twocol">
              <Panel title="ETA Prediction Trend">
                <Trend
                  data={j.updates.map((p) => ({
                    stage: label(p.stage),
                    delay: p.delay,
                    scheduled: 0,
                  }))}
                  x="stage"
                  series={[
                    { key: "delay", name: "Predicted delay", color: yellow },
                    { key: "scheduled", name: "Schedule", color: slate },
                  ]}
                  height={165}
                />
              </Panel>
              <Panel title="Operational Information">
                <Pairs
                  rows={[
                    ["Voyage", d.voyage_id],
                    ["Vessel", d.vessel],
                    ["Cargo", label(d.cargo)],
                    ["Latest report", label(pred.stage)],
                    [
                      "ETA revision",
                      hrs(j.updates.at(-1)?.change_from_previous),
                    ],
                  ]}
                />
              </Panel>
            </div>
          )}
          <div className={analysis ? "analysis-bottom" : ""}>
            {analysis ? <Panel title="Model Contributions"><p className="muted">Persistence carries the latest reported schedule deviation forward to final delivery.</p><Link className="inline" to={"/shipments/"+sid+"?"+qs({stage:chosen.stage,clock:at})}>Why this ETA? View evidence and model comparisons →</Link></Panel> : <ForecastEvidence estimate={pred} />}
            {analysis ? (
              <ScenarioPanel
                key={sid + cutoff}
                sid={sid}
                at={cutoff!}
                stage={chosen.stage}
                rows={j.milestones}
              />
            ) : (
              <Link className="inline" to={"/delay-analysis?"+qs({shipment:sid,stage:chosen.stage,clock:at})}>
                Inspect delay propagation →
              </Link>
            )}
          </div>
        </>
      )}
      {analysis && !historical && <Interactions at={cutoff || at} />}
    </article>
  );
}
export function Analysis() {
  const { at, meta } = useClock();
  const list = useApi<Page>("/shipments?" + qs({ as_of: at, size: 100 }));
  const [choice, setChoice] = useState(
    new URLSearchParams(location.search).get("shipment") ?? "",
  );
  const first =
    list.data?.items.find((r) => r.stage === "port_processing_complete") ??
    list.data?.items.find((r) => r.stage === "port_arrival") ??
    list.data?.items.find((r) => r.prediction) ??
    list.data?.items[0];
  const sid = choice || first?.shipment_id;
  return (
    <>
      <Heading
        title="Delay Analysis"
        sub="Follow stage delays, inspect recovered time, and compare operational scenarios."
      />
      <div className="controls">
        <label>
          Shipment
          <select
            aria-label="Analysis shipment"
            value={sid ?? ""}
            onChange={(e) => setChoice(e.target.value)}
          >
            {!sid && <option value="">Loading shipments…</option>}
            {meta.shipments.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>
      {sid ? (
        <JourneyView key={sid + at} sid={sid} analysis />
      ) : (
        <Wait {...list} />
      )}

    </>
  );
}
