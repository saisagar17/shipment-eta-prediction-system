import { useState } from "react";
import { Activity, Crosshair, Gauge, Timer } from "lucide-react";
import { useReducedMotion } from "framer-motion";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useApi } from "./api";
import { axis, Heading, label, Panel, Stats, Trend, Wait, yellow } from "./ui";
import type { Features, FrozenComparison } from "./types";
export function Performance() {
  const [split, setSplit] = useState("validation");
  const [model, setModel] = useState("E0");
  const metrics = useApi<FrozenComparison>("/model/comparison?split=" + split);
  const features = useApi<Features>("/model/features");
  const motion = !useReducedMotion(), d = metrics.data, score = d?.scores[model];
  const points = (d?.points ?? []).map(p => ({target_final_delay_hours: p.target_final_delay_hours, predicted:p[model+"_hours"]}));
  const bins = new Map<number, number>();
  for (const p of points) {
    const bin = Math.floor((p.predicted - p.target_final_delay_hours) / 2) * 2;
    bins.set(bin, (bins.get(bin) ?? 0) + 1);
  }
  return (
    <>
      <Heading
        title="Model Performance"
        sub="Compare final delivery delay estimates across models and reported stages."
        action={
          <label className="selectlabel">
            Evaluation partition
            <select value={split} onChange={(e) => setSplit(e.target.value)}>
              <option value="test">Held-out test</option>
              <option value="validation">Validation</option>
            </select>
          </label>
        }
      />
      {!d || !score ? (
        <Wait {...metrics} />
      ) : (
        <>
          <div className="controls"><label>Forecast for charts<select value={model} onChange={e=>setModel(e.target.value)}>{Object.entries(d.names).map(([k,v])=><option key={k} value={k}>{v} forecasts</option>)}</select></label><p className="muted">Persistence was selected on validation. The held-out test partition was previously inspected during development.</p></div>
          <Stats
            items={[
              {
                icon: Crosshair,
                title: d.names[model] + " MAE",
                value: score.mae.toFixed(2) + " h",
                accent: true,
              },
              {
                icon: Gauge,
                title: "Root mean squared error",
                value: score.rmse.toFixed(2) + " h",
              },
              {
                icon: Timer,
                title: "Median absolute error",
                value: score.median.toFixed(2) + " h",
              },
              {
                icon: Activity,
                title: "R² score",
                value: score.r2?.toFixed(2) ?? "—",
              },
            ]}
          />
          <div className="perfgrid">
            <Panel title="Model Comparison">
              <div className="tablewrap">
                <table>
                  <thead>
                    <tr>
                      {["Model", "MAE", "RMSE", "P90", "R²"].map((x) => (
                        <th key={x}>{x}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(d.scores)
                      .sort((a, b) => a[1].mae - b[1].mae)
                      .map(([k, v]) => (
                        <tr
                          key={k}
                          className={k === d.selected ? "selected" : ""}
                        >
                          <th scope="row">
                            {d.names[k]}
                            <progress
                              className="maebar"
                              aria-label={k + " MAE in hours"}
                              value={v.mae}
                              max={Math.max(
                                ...Object.values(d.scores).map(
                                  (s) => s.mae,
                                ),
                              )}
                            />
                          </th>
                          {[v.mae, v.rmse, v.p90, v.r2].map((x, i) => (
                            <td key={i}>{x?.toFixed(2) ?? "—"}</td>
                          ))}
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
              <small>
                Errors in hours · {score.n} snapshots · {score.shipments} shipments ·{" "}
                {score.voyages} voyages
              </small>
            </Panel>
            <Panel title="Actual vs. Predicted Delay">
              <div role="img" aria-label={`${d.names[model]} on ${split}: actual versus predicted delay for ${score.n} reports. ${score.within_4_pct.toFixed(1)}% of forecasts fell within four hours.`}>
              <div aria-hidden="true"><ResponsiveContainer width="100%" height={215}>
                <ScatterChart margin={{ left: -22, bottom: 4, right: 16 }}>
                  <CartesianGrid stroke="#e0e8e9" />
                  <XAxis
                    type="number"
                    dataKey="target_final_delay_hours"
                    name="Actual"
                    unit="h"
                    tick={axis}
                  />
                  <YAxis
                    type="number"
                    dataKey="predicted"
                    name="Predicted"
                    unit="h"
                    tick={axis}
                  />
                  <Tooltip cursor={{ strokeDasharray: "3 3" }} />
                  <Scatter
                    data={points}
                    fill={yellow}
                    opacity={0.65}
                    isAnimationActive={motion}
                    animationDuration={250}
                  />
                </ScatterChart>
              </ResponsiveContainer></div></div>
              <small>
                Horizontal · actual delay / Vertical · predicted delay
              </small>
            </Panel>
            <Panel title="Prediction Error Distribution">
              <ResponsiveContainer width="100%" height={215}>
                <BarChart
                  data={[...bins]
                    .sort((a, b) => a[0] - b[0])
                    .map(([bin, count]) => ({ bin, count }))}
                  margin={{ left: -24, right: 12 }}
                >
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="bin" tick={axis} unit="h" />
                  <YAxis tick={axis} />
                  <Tooltip />
                  <Bar
                    dataKey="count"
                    fill="#a4b9be"
                    radius={[3, 3, 0, 0]}
                    isAnimationActive={motion}
                    animationDuration={250}
                  />
                </BarChart>
              </ResponsiveContainer>
              <small>Predicted minus actual delay · two-hour bins</small>
            </Panel>
          </div>
          <div className="twocol">
            <Panel title="Global Feature Importance · Random Forest">
              {features.data ? (
                <div className="importance">
                  {features.data.importance.slice(0, 6).map((v) => (
                    <div key={v.feature}>
                      <span>{label(v.feature)}</span>
                      <progress
                        aria-label={label(v.feature) + " permutation importance in hours"}
                        value={Math.max(0, v.increase_mae)}
                        max={features.data!.importance[0].increase_mae}
                      />
                      <b>{v.increase_mae.toFixed(2)} h</b>
                    </div>
                  ))}
                </div>
              ) : (
                <Wait {...features} />
              )}
              <small>Mean increase in validation MAE after permutation</small>
            </Panel>
            <Panel title="Model Error by Shipment Stage">
              <Trend
                x="stage"
                data={["origin_departure","port_arrival","port_processing_complete","customs_clearance_complete"].map(stage => ({
                  stage: label(stage), ...Object.fromEntries(d.stages.filter(s=>s.stage===stage).map(s=>[s.candidate,s.mae]))
                }))}
                series={Object.entries(d.names).map(([key,name],i)=>({key,name:name+" MAE",color:[yellow,"#829eac","#277765","#984d30"][i]}))}
                height={170}
              />
            </Panel>
          </div>
          <Panel title="Accuracy windows and severe delays">
            <div className="tablewrap"><table><thead><tr>{["Model","Median |error| (h)","Within ±4 h","Within ±6 h","Within ±8 h","Severe shortfall (h)"].map(v=><th key={v}>{v}</th>)}</tr></thead>
            <tbody>{Object.entries(d.scores).map(([k,s])=><tr key={k}><th>{k} · {d.names[k]}</th><td>{s.median.toFixed(2)}</td>
              {[s.within_4_pct,s.within_6_pct,s.within_8_pct].map((v,i)=><td key={i}>{v.toFixed(1)}%</td>)}
              <td>{s.severe.mean_under.toFixed(2)}</td></tr>)}</tbody></table></div>
            <small>Mean severe shortfall is the positive part of actual minus forecast delay, averaged over {score.severe.n} reports from {score.severe.shipments} shipments delivered more than 6 h late. Overestimates count as zero.</small>
          </Panel>
          <p className="muted">The latest deviation already captures upstream delay. Residual boosters estimate the remaining gain or loss from observed operations. XGBoost reduced RMSE and severe shortfall on both partitions, while persistence retained the lowest MAE.</p>
          <p className="muted">
            Evaluation uses held-out synthetic shipment journeys. Results do not
            establish real-world deployment accuracy.
          </p>
        </>
      )}
    </>
  );
}
