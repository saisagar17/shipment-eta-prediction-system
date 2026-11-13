import { useState } from "react";
import { fmt, hrs, label, Panel, Pairs } from "./ui";
import type { Estimate, Journey, Milestone } from "./types";

export function ForecastEvidence({estimate}: {estimate: Estimate}) {
  const [selected, setSelected] = useState("E0");
  const model = estimate.comparisons[selected];
  const obs = estimate.observed;
  return <section className="why"><h2>Why This ETA?</h2>
    <p className="muted">The operational forecast adds the current reported deviation of {hrs(estimate.delay)} to the booked delivery time. It stays in effect until another milestone is reported.</p>
    <div className="twocol">
      <Panel title="Observed operational evidence">
        <Pairs rows={[
          ...Object.entries(estimate.reported_conditions).map(([stage,tag])=>[label(stage)+" report",label(tag)] as [string,string]),
          ["Departure deviation", hrs(obs.departure_delay_hours)],
          ["Port arrival deviation", hrs(obs.port_arrival_delay_hours)],
          ["Port processing deviation", hrs(obs.port_processing_delay_hours)],
          ["Latest deviation", hrs(obs.current_stage_delay_hours)],
          ["Time lost across reports", hrs(obs.cumulative_added_delay_hours)],
          ["Time gained across reports", hrs(obs.cumulative_recovered_hours)],
          ["Port handling duration", hrs(obs.known_port_processing_hours)],
          ["Customs duration", hrs(obs.known_customs_processing_hours)],
          ["Congestion index (0–1)", obs.observed_congestion_level?.toFixed(2) ?? "Unavailable"],
          ["Weather severity (0–1)", obs.observed_weather_severity?.toFixed(2) ?? "Unavailable"],
          ["Missing intermediate reports", obs.missing_event_count ?? "—"],
        ]}/><small>Durations require both endpoint reports. A dash means unavailable at this cutoff.</small>
      </Panel>
      <Panel title="Model Contributions">
        <label className="model-select">Inspect forecast<select aria-label="Inspect forecast" value={selected} onChange={e=>setSelected(e.target.value)}>
          {Object.entries(estimate.comparisons).map(([id,c])=><option key={id} value={id}>{c.name} · {id==="E0"?"operational":"comparison"}</option>)}
        </select></label>
        <Pairs rows={[["Delivery ETA · UTC", fmt(model.predicted_eta)], ["Predicted delay", hrs(model.delay)]]}/>
        <p className="muted">{model.local_method}</p>
        {selected !== "E0" && <>
          <h3>Largest local effects</h3>
          <Pairs rows={[
            ...(model.anchor_hours == null ? [] : [["Observed deviation", hrs(model.anchor_hours)] as [string,string]]),
            ["Model starting value", hrs(model.base_hours)],
            ...model.contributions.slice(0,5).map(c=>[label(c.feature)+(c.available?"":" (imputed)"),hrs(c.hours)] as [string,string]),
          ]}/>
          <details><summary>Global feature importance</summary><p className="muted">{model.global_method}</p>
          <Pairs rows={model.global_importance.slice(0,5).map(c=>[label(c.feature),hrs(c.value)])}/></details>
          <small>Signed local effects describe model associations. Correlated features can share credit.</small>
        </>}
      </Panel>
    </div>
  </section>;
}

export function Revisions({rows, updates, completed=false}: {rows:Milestone[];updates:Journey["updates"];completed?:boolean}) {
  return <Panel title={completed ? "Completed milestone ledger" : "Forecast revisions by report"}>
    <div className="tablewrap"><table><thead><tr>{["Milestone","Evidence","Deviation","Net change","Time gained",...(!completed?["Issued ETA · UTC","ETA revision"]:[])].map(v=><th key={v}>{v}</th>)}</tr></thead>
    <tbody>{rows.map(r=>{
      const update=updates.find(u=>u.stage===r.stage);
      return <tr key={r.stage}><th scope="row">{label(r.stage)}</th><td>{r.across_gap?"Across reporting gap":label(r.state)}</td>
        <td>{hrs(r.deviation)}</td><td>{hrs(r.change)}</td><td>{hrs(r.recovered)}</td>
        {!completed && <><td>{fmt(update?.predicted_eta)}</td><td>{hrs(update?.change_from_previous)}</td></>}
      </tr>;
    })}</tbody></table></div>
    <small>{completed?"Changes here use physical stage times, including stages absent from tracking. Final delivery closes the forecast.":"Departure sets the starting deviation. A change across a gap belongs to the whole interval between reports."}</small>
  </Panel>;
}
