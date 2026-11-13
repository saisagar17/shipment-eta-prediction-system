import { useState } from "react";
import { useReducedMotion } from "framer-motion";
import {
  CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from "recharts";
import { qs, useApi } from "./api";
import { axis, hrs, label, Panel, useClock, Wait } from "./ui";

interface Relationships {
  observed_shipments: number;
  port_correlation: number | null;
  port_calls: {voyage: string; congestion: number; processing_hours: number; pairs: number}[];
  departure_groups: {group: string; shipments: number; increased: number; mean_change_hours: number | null}[];
  routes: {route: string; shipments: number; voyages: number; median_hours: number; min_hours: number; max_hours: number}[];
  recovery: {stage: string; pairs: number; recovered: number; mean_recovered_hours: number | null}[];
  gaps: {stage: string; reached: number; missing: number}[];
}

const topics = [
  "Port congestion", "Departure to customs", "Route variability", "Recovery by stage", "Tracking gaps",
] as const;
type Topic = typeof topics[number];

function SummaryTable({headers, rows}: {headers: string[]; rows: (string | number)[][]}) {
  return <div className="tablewrap"><table>
    <thead><tr>{headers.map(h => <th key={h} scope="col">{h}</th>)}</tr></thead>
    <tbody>{rows.map(row => <tr key={row[0]}>{row.map((value, i) =>
      <td key={headers[i]}>{value}</td>)}</tr>)}</tbody>
  </table></div>;
}

function RelationshipsView({topic, data}: {topic: Topic; data: Relationships}) {
  const reduced = useReducedMotion();
  const { meta } = useClock();
  if (topic === "Port congestion") {
    const r = data.port_correlation;
    return <>
      <p className="muted">Each point pairs one voyage’s released congestion reading with its mean handling time across shipments reporting both port arrival and processing completion.</p>
      {data.port_calls.length ? <>
        <div role="img" aria-label={`Congestion index and mean handling hours for ${data.port_calls.length} port calls. Individual values follow in the port call table.`}>
        <div aria-hidden="true"><ResponsiveContainer width="100%" height={190}>
          <ScatterChart margin={{top: 12, left: 6, right: 25, bottom: 16}}>
            <CartesianGrid vertical={false} stroke="#dce5e7"/>
            <XAxis dataKey="congestion" type="number" domain={[0, 1]} tick={axis}
              name="Congestion index" label={{value:"Congestion index (0–1)", position:"insideBottom", offset:-10, ...axis}}/>
            <YAxis dataKey="processing_hours" type="number" name="Handling time" unit=" h" tick={axis}/>
            <Tooltip content={({active, payload}) => {
              const point = payload?.[0]?.payload as Relationships["port_calls"][number] | undefined;
              return active && point ? <div className="panel">
                <strong>{point.voyage}</strong><p>Congestion index {point.congestion.toFixed(2)}</p>
                <p>{point.processing_hours.toFixed(1)} h mean handling · {point.pairs} paired reports</p>
              </div> : null;
            }}/>
            <Scatter data={data.port_calls} fill="#877000" isAnimationActive={!reduced} animationDuration={240}/>
          </ScatterChart>
        </ResponsiveContainer></div></div>
        <small>{data.port_calls.length} port calls. {r === null
          ? "A correlation requires three paired calls and variation on both axes."
          : `Pearson r = ${r.toFixed(2)}. ${r > 0 ? "Higher congestion was associated with longer mean handling times" : r < 0 ? "Higher congestion was associated with shorter mean handling times" : "The observed linear association was zero"} in this sample. Other differences between voyages may also matter.`}</small>
        <details><summary>Port call values</summary><SummaryTable
          headers={["Voyage", "Congestion index", "Mean handling (h)", "Shipment pairs"]}
          rows={data.port_calls.map(c => [c.voyage, c.congestion.toFixed(2), c.processing_hours.toFixed(1), c.pairs])}/></details>
      </> : <p className="empty">No port call has both released measurements and a complete handling interval at this time.</p>}
    </>;
  }
  if (topic === "Departure to customs") return <>
    <p className="muted">Compare each shipment’s customs deviation with its departure deviation. A positive net change means the shipment lost schedule time between the two reports. An intermediate gap prevents assigning that loss to a particular stage.</p>
    <SummaryTable headers={["Departure group", "Paired shipments", "Shipments losing time", "Mean net change"]}
      rows={data.departure_groups.map(g => [g.group, g.shipments, g.increased, hrs(g.mean_change_hours)])}/>
  </>;
  if (topic === "Route variability") return <>
    <p className="muted">Compare routes at the same milestone, port processing completion. The range shows how far individual shipment reports fell on either side of their booked schedule. Shipments can share a voyage.</p>
    {data.routes.length ? <SummaryTable headers={["Route", "Shipments", "Voyages", "Median deviation", "Range"]}
      rows={data.routes.map(r => {
        const route = meta.routes.find(item => item.route_id === r.route);
        const name = route ? `${route.origin} → ${route.destination_port} → ${route.final_destination}` : r.route;
        return [name, r.shipments, r.voyages, hrs(r.median_hours), `${hrs(r.min_hours)} to ${hrs(r.max_hours)}`];
      })}/>
      : <p className="empty">No processing completion reports have arrived.</p>}
  </>;
  if (topic === "Recovery by stage") return <>
    <p className="muted">Recovery measures pre-existing lateness removed between consecutive reports. Catching up to schedule exhausts that balance. Each mean includes intervals with zero recovery.</p>
    <SummaryTable headers={["Interval ending at", "Paired shipments", "Shipments recovering time", "Mean hours recovered"]}
      rows={data.recovery.map(s => [label(s.stage), s.pairs, s.recovered, s.mean_recovered_hours?.toFixed(1) ?? "—"])}/>
  </>;
  return <>
    <p className="muted">A gap becomes observable when a later report arrives before an intermediate one. Missing reports prevent stage-specific time attribution.</p>
    <SummaryTable headers={["Milestone", "Shipments known to have reached stage", "Shipments with a gap"]}
      rows={data.gaps.map(s => [label(s.stage), s.reached, s.missing])}/>
  </>;
}

export function Interactions({at}: {at: string}) {
  const [topic, setTopic] = useState<Topic>("Port congestion");
  const result = useApi<Relationships>("/analysis/interactions?" + qs({as_of: at}));
  return <Panel title="Fleet logistics relationships" action={
    <select aria-label="Fleet relationship" value={topic} onChange={e => setTopic(e.target.value as Topic)}>
      {topics.map(t => <option key={t}>{t}</option>)}
    </select>
  }>
    {result.data ? <>
      <small>{result.data.observed_shipments} held-out shipments with a report by {new Date(at).toISOString().slice(0,19).replace("T"," ")} UTC</small>
      <RelationshipsView topic={topic} data={result.data}/>
    </> : <Wait {...result}/>}
  </Panel>;
}
