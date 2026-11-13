import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const time = "2025-07-07T12:00:00Z";
const meta = {
  routes: [],
  vessels: [],
  stages: ["origin_departure", "port_arrival"],
  shipments: ["SHP-T"],
  start: time,
  end: time,
  default_time: time,
};
const prediction = {
  delay: 3,
  predicted_eta: time,
  stage: "port_arrival",
  risk: "Moderate",
  scheduled_eta: time,
};
const row = {
  shipment_id: "SHP-T",
  voyage_id: "V-test",
  route_id: "R01",
  vessel: "Ship A",
  cargo: "electronics",
  route: "Test corridor",
  scheduled_eta: time,
  stage: "port_arrival",
  status: "In transit",
  prediction,
};
const dash = {
  total: 1,
  active: 1,
  delivered: 0,
  average: 3,
  on_time: 0,
  risks: { Low: 0, Moderate: 1, High: 0 },
  stages: { port_arrival: 1 },
  trend: [],
  attention: [row],
};
const fixture = (path: string) => {
  if (path.startsWith("/metadata")) return meta;
  if (path.startsWith("/dashboard")) return dash;
  if (path.startsWith("/shipments?"))
    return {
      items: path.includes("search=nope") ? [] : [row],
      total: path.includes("search=nope") ? 0 : 1,
      page: 1,
    };
  if (path.startsWith("/shipments/SHP-T")) return { ...row, milestones: [] };
  return {};
};
function open(path: string) {
  render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <App />
    </MemoryRouter>,
  );
}
describe("Shipment application", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async (url: string) =>
          new Response(JSON.stringify(fixture(url.replace("/api", "")))),
      ),
    );
  });
  it("renders exactly four navigation links and the API dashboard", async () => {
    open("/dashboard");
    expect(
      within(screen.getByRole("navigation")).getAllByRole("link"),
    ).toHaveLength(4);
    expect(
      await screen.findByText("Shipments Requiring Attention"),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "SHP-T" })).toBeTruthy();
  });
  it("opens shipment details with Shipments active", async () => {
    open("/dashboard");
    await userEvent.click(await screen.findByRole("link", { name: "SHP-T" }));
    expect(await screen.findByText("Reveal completed history")).toBeTruthy();
    expect(
      screen
        .getByRole("link", { name: "Shipments" })
        .getAttribute("aria-current"),
    ).toBe("page");
  });
  it("filters the shipment list through the API", async () => {
    open("/shipments");
    await userEvent.type(
      await screen.findByLabelText("Search shipment ID"),
      "nope",
    );
    expect(
      await screen.findByText("No matching shipments at this time."),
    ).toBeTruthy();
  });
  it("shows a loading state for a pending connection", () => {
    vi.stubGlobal("fetch", () => new Promise(() => {}));
    open("/dashboard");
    expect(screen.getByRole("status").getAttribute("aria-label")).toBe(
      "Loading",
    );
  });
  it("exposes API errors and a retry", async () => {
    vi.stubGlobal(
      "fetch",
      async () =>
        new Response(JSON.stringify({ detail: "Model is unavailable" }), {
          status: 503,
        }),
    );
    open("/dashboard");
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Model is unavailable",
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });
});
