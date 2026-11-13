import { createContext, useContext, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import { CalendarDays, type LucideIcon } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Metadata, Risk, Shipment } from "./types";

export const names: Record<string, string> = {
  origin_departure: "Departure",
  port_arrival: "Port arrival",
  port_processing_complete: "Port processing",
  customs_clearance_complete: "Customs",
  final_delivery: "Final delivery",
  not_started: "Awaiting departure",
};
export const label = (s: string) =>
  names[s] || s.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
export const fmt = (value: string | null | undefined) =>
  value
    ? new Intl.DateTimeFormat("en-GB", {
        timeZone: "UTC",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
      }).format(new Date(value))
    : "—";
export const hrs = (v: number | null | undefined) =>
  v == null ? "—" : (v > 0 ? "+" : "") + v.toFixed(1) + " h";
export const ClockContext = createContext<{
  meta: Metadata;
  at: string;
  setAt: (s: string) => void;
} | null>(null);
export const useClock = () => useContext(ClockContext)!;
export function Clock() {
  const { meta, at, setAt } = useClock();
  const local = (s: string) => new Date(s).toISOString().slice(0, 16);
  return (
    <label className="clock">
      <CalendarDays size={21} />
      <span>
        Simulation time · UTC
        <input
          type="datetime-local"
          aria-label="Simulation time UTC"
          value={local(at)}
          min={local(meta.start)}
          max={local(meta.end)}
          onChange={(e) => {
            if (e.target.value && e.target.validity.valid)
              setAt(new Date(e.target.value + "Z").toISOString());
          }}
        />
      </span>
    </label>
  );
}
export function Heading({
  title,
  sub,
  action,
}: {
  title: string;
  sub: string;
  action?: ReactNode;
}) {
  return (
    <header className="pagehead">
      <div>
        <h1>{title}</h1>
        <p>{sub}</p>
      </div>
      {action ?? <Clock />}
    </header>
  );
}
export function Wait({ error, retry }: { error?: string; retry?: () => void }) {
  return error ? (
    <div className="notice" role="alert">
      {error} <button onClick={retry}>Retry</button>
    </div>
  ) : (
    <div className="skeleton" role="status" aria-label="Loading">
      Loading…
    </div>
  );
}
export function Panel({
  title,
  action,
  children,
  cls = "",
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
  cls?: string;
}) {
  return (
    <section className={"panel " + cls}>
      <header>
        <h2>{title}</h2>
        {action}
      </header>
      {children}
    </section>
  );
}
export function Stats({
  items,
}: {
  items: {
    icon: LucideIcon;
    value: string | number;
    title: string;
    accent?: boolean;
  }[];
}) {
  const reduced = useReducedMotion();
  return (
    <div className="stats">
      {items.map(({ icon: Icon, value, title, accent }, i) => (
        <motion.div
          className={"stat " + (accent ? "tint" : "")}
          key={title}
          initial={reduced ? false : { opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2, delay: reduced ? 0 : 0.035 * i }}
        >
          <span className="icon">
            <Icon size={24} strokeWidth={1.55} />
          </span>
          <div>
            <strong className="value-update" key={String(value)}>{value}</strong>
            <small>{title}</small>
          </div>
        </motion.div>
      ))}
    </div>
  );
}
export function Badge({ risk }: { risk?: Risk }) {
  return risk ? (
    <span
      title="Predicted final delay: Low ≤2 h, Moderate >2 to 6 h, High >6 h."
      className={"badge " + risk.toLowerCase()}
    >
      {risk}
    </span>
  ) : (
    <>—</>
  );
}
export function Stage({ value }: { value: string }) {
  return <span className={"stage " + value}>{label(value)}</span>;
}
export function Table({
  rows,
  full = false,
  selected,
}: {
  rows: Shipment[];
  full?: boolean;
  selected?: string;
}) {
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            {[
              "Shipment ID",
              ...(full ? ["Voyage", "Vessel"] : []),
              "Route",
              "Current stage",
              "Scheduled ETA",
              "Predicted ETA",
              "Delay",
              "Risk",
              ...(!full ? ["Reason for attention"] : []),
            ].map((t) => (
              <th key={t}>{t}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.shipment_id}
              className={r.shipment_id === selected ? "selected" : ""}
            >
              <td>
                <Link to={"/shipments/" + r.shipment_id}>{r.shipment_id}</Link>
              </td>
              {full && (
                <>
                  <td>{r.voyage_id}</td>
                  <td>{r.vessel}</td>
                </>
              )}
              <td>{r.route}</td>
              <td>
                <Stage value={r.stage} />
              </td>
              <td>{fmt(r.scheduled_eta)}</td>
              <td>{fmt(r.prediction?.predicted_eta)}</td>
              <td>{hrs(r.prediction?.delay)}</td>
              <td>
                <Badge risk={r.prediction?.risk} />
              </td>
              {!full && <td className="reason">{r.attention_reasons?.join(" ")}</td>}
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && (
        <p className="empty">No matching shipments at this time.</p>
      )}
    </div>
  );
}
export const yellow = "#e0be00",
  slate = "#829eac";
export const axis = { fontSize: 11, fill: "#506169" };
export function Trend({
  data,
  x,
  series,
  height = 218,
}: {
  data: object[];
  x: string;
  series: { key: string; name: string; color: string }[];
  height?: number;
}) {
  const reduced = useReducedMotion();
  return (
    <>
      <div className="legend">
        {series.map((s) => (
          <span key={s.key}>
            <i style={{ background: s.color }} />
            {s.name}
          </span>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart
          data={data}
          margin={{ top: 12, right: 24, bottom: 0, left: -20 }}
        >
          <CartesianGrid vertical={false} stroke="#dce5e7" />
          <XAxis dataKey={x} tick={axis} tickLine={false} />
          <YAxis tick={axis} tickLine={false} unit="h" />
          <Tooltip
            formatter={(v) => (typeof v === "number" ? v.toFixed(2) + " h" : v)}
          />
          {series.map((s) => (
            <Line
              key={s.key}
              dataKey={s.key}
              name={s.name}
              stroke={s.color}
              strokeWidth={2.5}
              dot={{ r: 3.5, fill: "#fff", strokeWidth: 2 }}
              type="linear"
              connectNulls={false}
              isAnimationActive={!reduced}
              animationDuration={240}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}
export function Pairs({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="pairs">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}
