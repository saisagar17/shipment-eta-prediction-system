import { Link } from "react-router-dom";
import { Activity, ArrowRight, Box, Clock3, TriangleAlert } from "lucide-react";
import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";
import { useReducedMotion } from "framer-motion";
import { useApi, qs } from "./api";
import {
  Heading,
  hrs,
  label,
  Panel,
  Stats,
  Table,
  Trend,
  useClock,
  Wait,
  yellow,
  slate,
} from "./ui";
import type { DashboardData, Risk } from "./types";
export function Dashboard() {
  const { at } = useClock(),
    q = useApi<DashboardData>("/dashboard?" + qs({ as_of: at })),
    d = q.data;
  const reduced = useReducedMotion();
  const colors: Record<Risk, string> = {
    High: "#e5717e",
    Moderate: "#f5da28",
    Low: "#a3babf",
  };
  return (
    <>
      <Heading
        title="Shipment Operations Overview"
        sub="Track held-out shipments, predict delivery times, and follow delays."
      />
      {!d ? (
        <Wait {...q} />
      ) : (
        <>
          <Stats
            items={[
              { icon: Box, value: d.total, title: "Total shipments" },
              { icon: Activity, value: d.active, title: "In progress" },
              {
                icon: Clock3,
                value: hrs(d.average),
                title: "Average predicted delay",
              },
              {
                icon: TriangleAlert,
                value: d.risks.High,
                title: "High delay risk",
              },
            ]}
          />
          <div className="dashgrid">
            <Panel title="Predicted vs. Observed Delay" cls="trendcard">
              <p className="muted">
                Daily mean at report time · the persistence forecast follows the observed deviation, so the two lines overlap.
              </p>
              {d.trend.length ? (
                <Trend
                  data={d.trend.map((x) => ({ ...x, date: x.date.slice(5) }))}
                  x="date"
                  series={[
                    {
                      key: "predicted",
                      name: "Predicted final delay",
                      color: yellow,
                    },
                    {
                      key: "observed",
                      name: "Observed stage delay",
                      color: slate,
                    },
                  ]}
                  height={235}
                />
              ) : (
                <p className="empty">No milestone reports in this period.</p>
              )}
            </Panel>
            <Panel title="On-Time Outlook">
              <div
                className="gauge"
                role="img"
                aria-label="Predicted on-time share"
              >
                <svg viewBox="0 0 180 96">
                  <path
                    d="M 14 82 A 76 76 0 0 1 166 82"
                    pathLength="100"
                    fill="none"
                    stroke="#dce5e7"
                    strokeWidth="13"
                    strokeLinecap="round"
                  />
                  <path
                    d="M 14 82 A 76 76 0 0 1 166 82"
                    pathLength="100"
                    fill="none"
                    stroke="#f4dc21"
                    strokeWidth="13"
                    strokeLinecap="round"
                    strokeDasharray={(d.on_time ?? 0) * 100 + " 100"}
                  />
                </svg>
                <strong>
                  {d.on_time == null ? "—" : Math.round(100 * d.on_time) + "%"}
                </strong>
              </div>
              <p className="center muted">Active ETAs at or before schedule</p>
            </Panel>
            <Panel title="Delay Risk Distribution">
              <div className="riskplot">
                <div className="donut" aria-hidden="true">
                  <ResponsiveContainer width="100%" height={125}>
                    <PieChart>
                      <Pie
                        rootTabIndex={-1}
                        data={Object.entries(d.risks).map(([name, value]) => ({
                          name,
                          value,
                        }))}
                        dataKey="value"
                        innerRadius="70%"
                        outerRadius="92%"
                        stroke="none"
                        isAnimationActive={!reduced}
                        animationDuration={260}
                      >
                        {Object.keys(d.risks).map((k) => (
                          <Cell key={k} fill={colors[k as Risk]} />
                        ))}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                  <b>{d.active}</b>
                </div>
                <div>
                  {(["High", "Moderate", "Low"] as Risk[]).map((k) => (
                    <p key={k}>
                      <i style={{ background: colors[k] }} />
                      {k} <b>{d.risks[k]}</b>
                    </p>
                  ))}
                </div>
              </div>
            </Panel>
            <Panel title="Completed Deliveries" cls="tint">
              <div className="bigmetric">
                {d.delivered}
                <small> / {d.total}</small>
              </div>
              <p className="center muted">Delivery reports received</p>
            </Panel>
            <Panel title="Active Shipments by Stage">
              <div className="bars">
                {Object.entries(d.stages).map(([k, n]) => (
                  <div key={k}>
                    <span>{label(k)}</span>
                    <progress
                      aria-label={label(k) + " active shipments"}
                      value={n}
                      max={Math.max(1, ...Object.values(d.stages))}
                    />
                    <b>{n}</b>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
          <Panel
            title="Shipments Requiring Attention"
            action={
              <Link className="inline" to="/shipments">
                View all <ArrowRight size={15} />
              </Link>
            }
          >
            <p className="muted">Active shipments with delay above 2 h, increasing deviation, or a confirmed tracking gap. High risk means a forecast more than 6 h late.</p>
            <Table rows={d.attention} />
          </Panel>
        </>
      )}
    </>
  );
}
