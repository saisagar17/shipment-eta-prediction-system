import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { qs, useApi } from "./api";
import { Badge, Heading, label, Stage, Table, useClock, Wait } from "./ui";
import { JourneyView } from "./Journey";
import type { Page } from "./types";
export function Shipments() {
  const { shipmentId } = useParams(),
    { meta, at, setAt } = useClock();
  const [filters, setFilters] = useState({
      search: "",
      route: "",
      vessel: "",
      stage: "",
      risk: "",
    }),
    [page, setPage] = useState(1);
  const list = useApi<Page>(
    "/shipments?" + qs({ ...filters, as_of: at, page, size: 8 }),
  );
  function update(key: keyof typeof filters, value: string) {
    setFilters({ ...filters, [key]: value });
    setPage(1);
  }
  const select = (
    key: "route" | "vessel" | "stage" | "risk",
    options: string[],
  ) => (
    <label key={key}>
      {label(key)}
      <select
        value={filters[key]}
        onChange={(e) => update(key, e.target.value)}
      >
        <option value="">
          All {key === "risk" ? "risk levels" : key + "s"}
        </option>
        {options.map((x) => (
          <option key={x} value={x}>
            {label(x)}
          </option>
        ))}
      </select>
    </label>
  );
  return (
    <>
      <Heading
        title="Shipments"
        sub="Find a consignment, replay its milestones, and inspect its delivery estimate."
      />
      {meta.demonstrations?.length ? <div className="demo-links" aria-label="Illustrative test journeys">
        <b>Replay a shipment</b>
        {meta.demonstrations.map((demo) => <Link key={demo.id} to={"/shipments/"+demo.id}
          onClick={() => setAt(demo.as_of)}>{demo.type} · {demo.id}</Link>)}
      </div> : null}
      <div className={shipmentId ? "splitpane" : "singlepane"}>
        <section className="panel">
          <div className="search">
            <Search size={18} />
            <input
              aria-label="Search shipment ID"
              placeholder="Search by shipment ID"
              value={filters.search}
              onChange={(e) => update("search", e.target.value)}
            />
          </div>
          <div className="filters">
            {select(
              "route",
              meta.routes.map((x) => x.route_id),
            )}
            {select("vessel", meta.vessels)}
            {select("stage", ["not_started", ...meta.stages])}
            {select("risk", ["Low", "Moderate", "High"])}
          </div>
          {!list.data ? (
            <Wait {...list} />
          ) : (
            <>
              {shipmentId ? (
                <div className="tablewrap">
                  <table>
                    <thead>
                      <tr>
                        {["Shipment ID", "Route", "Stage", "Risk"].map((x) => (
                          <th key={x}>{x}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {list.data.items.map((r) => (
                        <tr
                          className={
                            shipmentId === r.shipment_id ? "selected" : ""
                          }
                          key={r.shipment_id}
                        >
                          <td>
                            <Link to={"/shipments/" + r.shipment_id}>
                              {r.shipment_id}
                            </Link>
                          </td>
                          <td>{r.route_id}</td>
                          <td>
                            <Stage value={r.stage} />
                          </td>
                          <td>
                            <Badge risk={r.prediction?.risk} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {!list.data.total && (
                    <p className="empty">No matching shipments.</p>
                  )}
                </div>
              ) : (
                <Table rows={list.data.items} full />
              )}
              <div className="pager">
                <span>
                  {list.data.total
                    ? (page - 1) * 8 +
                      1 +
                      "–" +
                      Math.min(page * 8, list.data.total)
                    : "0"}{" "}
                  of {list.data.total}
                </span>
                <button
                  aria-label="Previous page"
                  disabled={page === 1}
                  onClick={() => setPage(page - 1)}
                >
                  <ChevronLeft size={16} />
                </button>
                <b>{page}</b>
                <button
                  aria-label="Next page"
                  disabled={page * 8 >= list.data.total}
                  onClick={() => setPage(page + 1)}
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </>
          )}
        </section>
        {shipmentId && <JourneyView key={shipmentId + at} sid={shipmentId} />}
      </div>
    </>
  );
}
