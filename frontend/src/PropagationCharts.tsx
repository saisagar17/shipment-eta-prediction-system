import { useReducedMotion } from "framer-motion";
import {
  Area,
  AreaChart,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Milestone } from "./types";
import { axis, label, Panel, slate, yellow } from "./ui";

export function PropagationCharts({ rows }: { rows: Milestone[] }) {
  const motion = !useReducedMotion();
  let added = 0,
    recovered = 0;
  const values = rows.map((m) => {
    added += m.added ?? 0;
    recovered += m.recovered ?? 0;
    return {
      stage: label(m.stage),
      deviation: m.deviation,
      change: m.across_gap ? null : m.change,
      additions: m.deviation === null ? null : added,
      recovery: m.deviation === null ? null : recovered,
    };
  });
  const axes = (
    <>
      <CartesianGrid vertical={false} stroke="#dce5e7" />
      <XAxis dataKey="stage" tick={axis} tickLine={false} />
      <YAxis tick={axis} tickLine={false} unit="h" />
      <Tooltip formatter={(n) => Number(n).toFixed(2) + " h"} />
    </>
  );
  return (
    <div className="twocol">
      <Panel title="Stage-wise Delay Propagation">
        <div className="legend">
          <span>
            <i style={{ background: yellow }} />
            Observed deviation
          </span>
          <span>
            <i style={{ background: slate }} />
            Interval change
          </span>
        </div>
        <ResponsiveContainer width="100%" height={205}>
          <ComposedChart data={values} margin={{ left: -20, right: 20 }}>
            {axes}
            <Bar
              dataKey="change"
              name="Interval change"
              fill={slate}
              maxBarSize={40}
              radius={[3, 3, 0, 0]}
              isAnimationActive={motion}
              animationDuration={240}
            />
            <Line
              dataKey="deviation"
              name="Observed deviation"
              stroke={yellow}
              strokeWidth={3}
              dot={{ r: 4, fill: "white" }}
              isAnimationActive={motion}
              animationDuration={240}
            />
          </ComposedChart>
        </ResponsiveContainer>
        {rows
          .filter((m) => m.across_gap)
          .map((m) => (
            <p className="muted" key={m.stage}>
              Across report gap to {label(m.stage)} · {m.change!.toFixed(2)} h
              net change.
            </p>
          ))}
      </Panel>
      <Panel title="Added Delay and Recovery">
        <div className="legend">
          <span>
            <i style={{ background: slate }} />
            Cumulative additions
          </span>
          <span>
            <i style={{ background: yellow }} />
            Cumulative recoveries
          </span>
        </div>
        <ResponsiveContainer width="100%" height={205}>
          <AreaChart data={values} margin={{ left: -20, right: 20 }}>
            {axes}
            <Area
              dataKey="additions"
              name="Cumulative additions"
              stroke={slate}
              fill="#c2d3d6"
              fillOpacity={0.55}
              dot={{ r: 3 }}
              isAnimationActive={motion}
              animationDuration={240}
            />
            <Area
              dataKey="recovery"
              name="Cumulative recoveries"
              stroke={yellow}
              fill="#f7e97e"
              fillOpacity={0.65}
              dot={{ r: 3 }}
              isAnimationActive={motion}
              animationDuration={240}
            />
          </AreaChart>
        </ResponsiveContainer>
        <p className="muted">
          Starting departure deviation is excluded from both totals.
        </p>
      </Panel>
    </div>
  );
}
