import { test, expect } from "@playwright/test";

test("real dashboard, filtered list, shipment replay and historical reveal", async ({
  page,
  request,
}) => {
  const meta = await (await request.get("/api/metadata")).json();
  const manifest = await (await request.get("/api/shipments?size=100")).json();
  const sid = manifest.items.find((r: { stage: string }) =>
    ["port_processing_complete", "customs_clearance_complete"].includes(
      r.stage,
    ),
  ).shipment_id;
  await page.goto("/dashboard");
  await expect(
    page.getByRole("heading", { name: "Shipments Requiring Attention" }),
  ).toBeVisible();
  await expect(page.getByRole("navigation").getByRole("link")).toHaveCount(4);
  await page.getByRole("navigation").getByText("Shipments").click();
  await page.getByLabel("Search shipment ID").fill(sid);
  await page.getByRole("link", { name: sid, exact: true }).click();
  await expect(
    page.getByRole("link", { name: "Shipments", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  const stage = page.getByLabel("Reported prediction stage");
  await stage.selectOption("origin_departure");
  await expect(
    page.getByRole("heading", { name: "ETA Prediction Trend" }),
  ).toBeVisible();
  await expect(page.locator(".timeline .done")).toHaveCount(1);
  await expect(page.locator(".timeline li")).toHaveCount(5);
  await page.getByText("Reveal completed history").click();
  await expect(page.getByText("Historical completed journey")).toBeVisible();
  await expect(page.getByText(/Actual final delivery/)).toBeVisible();
  await page.getByText("Return to replay").click();
  await expect(page.getByText(/Actual final delivery/)).toHaveCount(0);
  expect(meta.stages.length).toBe(5);
});

test("analysis uses real predictions and supports hypothetical next intervals", async ({
  page,
}) => {
  await page.goto("/delay-analysis");
  await page
    .getByLabel("Reported prediction stage")
    .selectOption("origin_departure");
  await expect(
    page.getByRole("heading", { name: "Stage-wise Delay Propagation" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Compare ETAs" }).click();
  await expect(page.getByText("Hypothetical delay change")).toBeVisible();
  await expect(
    page.getByText("Model Contributions", { exact: true }),
  ).toBeVisible();
});

test("a missing report stays distinct from an upcoming milestone", async ({
  page,
  request,
}) => {
  const meta = await (await request.get("/api/metadata")).json();
  let match = "";
  for (const sid of meta.shipments) {
    const history = await (
      await request.get(
        "/api/shipments/" + sid + "?as_of=" + encodeURIComponent(meta.end),
      )
    ).json();
    if (
      history.milestones.some(
        (m: { state: string; order: number }) =>
          m.state === "observation_gap" && m.order < 3,
      ) &&
      history.milestones[3].released
    ) {
      match = sid;
      break;
    }
  }
  expect(match).toBeTruthy();
  await page.goto("/shipments/" + match);
  await page.getByLabel("Simulation time UTC").fill(meta.end.slice(0, 16));
  await page
    .getByLabel("Reported prediction stage")
    .selectOption("customs_clearance_complete");
  await expect(
    page.getByText("Observation gap", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.locator(".timeline")).toContainText("Pending");
});

test("performance loads saved results and mobile navigation fits", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/model-performance");
  await expect(
    page.getByRole("heading", { name: "Model Comparison" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Prediction Error Distribution" }),
  ).toBeVisible();
  await expect(page.getByText("Current delay", { exact: true })).toBeVisible();
  await page.getByLabel("Evaluation partition").selectOption("validation");
  await expect(page.getByText(/87 snapshots/)).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(391);
});
