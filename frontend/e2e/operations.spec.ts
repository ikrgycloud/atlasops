import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
const env = readFileSync(resolve(import.meta.dirname, "../../.env"), "utf8");
const secret = env
  .split("\n")
  .find((x) => x.startsWith("ATLAS_DEV_AUTH_SECRET="))
  ?.split("=")[1];
const fixture = JSON.parse(
  readFileSync(
    resolve(import.meta.dirname, "../../.local/e2e-fixture.json"),
    "utf8",
  ),
) as { email: string };
if (!secret)
  throw new Error(
    "Generate a local development .env before running browser tests",
  );

test("browser incident, investigation, explicit approval, verified execution, and report", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByLabel("Email", { exact: true }).fill(fixture.email);
  await page.getByLabel("Development secret").fill(secret);
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Operations overview" }),
  ).toBeVisible();
  await expect(page.getByText("DEMO WORKSPACE", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Incidents", exact: true }).click();
  await page.getByRole("button", { name: "Ingest synthetic alert" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Sample API error rate exceeds threshold",
    }),
  ).toBeVisible();
  // Never make paid/live model calls in this browser suite, even after a user sets a key.
  await page.getByLabel("Use configured AI provider").uncheck();
  await page.getByRole("button", { name: "Collect & investigate" }).click();
  await expect(
    page
      .getByText("AI investigation is unavailable.", { exact: false })
      .first(),
  ).toBeVisible({ timeout: 45000 });
  await expect(page.getByLabel("Investigation limits").first()).toContainText(
    "0/4 model iterations",
  );
  await page
    .getByText("Source coverage and freshness", { exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("cell", { name: "metrics", exact: false }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Propose sandbox recovery" }).click();
  await page.getByRole("combobox").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Submit for approval" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByRole("link", { name: "Approval inbox", exact: true }).click();
  await page.getByRole("button", { name: "Review & approve" }).first().click();
  await expect(
    page.getByRole("dialog", { name: "Confirm explicit approval" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "I approve this exact plan" }).click();
  await page.getByRole("button", { name: "Prepare execution" }).first().click();
  await page
    .getByRole("button", { name: "Confirm sandbox execution" })
    .first()
    .click();
  await expect(
    page.getByText("SUCCEEDED", { exact: true }).first(),
  ).toBeVisible({ timeout: 45000 });
  await page.getByRole("link", { name: "Daily reports", exact: true }).click();
  await page
    .getByLabel("Report date")
    .fill(new Date().toISOString().slice(0, 10));
  const generated = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/reports/generate") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Generate report" }).click();
  const job = (await (await generated).json()) as { job_id: string };
  const token = await page.evaluate(() =>
    sessionStorage.getItem("atlasops-token"),
  );
  await expect
    .poll(
      async () => {
        const response = await page.request.get(`/api/v1/jobs/${job.job_id}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        return (await response.json()).status;
      },
      { timeout: 45000 },
    )
    .toBe("SUCCEEDED");
  await page.reload();
  await expect(
    page.getByRole("link", { name: /Daily operations report/ }).first(),
  ).toBeVisible({ timeout: 45000 });
  await page
    .getByRole("link", { name: /Daily operations report/ })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Executive summary" }),
  ).toBeVisible();
  await expect(
    page.getByText("SUCCEEDED", { exact: true }).first(),
  ).toBeVisible();
  expect(errors).toEqual([]);
  await page.screenshot({
    path: "../.local/operations-report.png",
    fullPage: true,
  });
});

test("tablet dashboard and API-backed navigation", async ({ page }) => {
  await page.setViewportSize({ width: 820, height: 1180 });
  await page.goto("/");
  await page.getByLabel("Email", { exact: true }).fill(fixture.email);
  await page.getByLabel("Development secret").fill(secret);
  await page.getByRole("button", { name: "Enter workspace" }).click();
  for (const name of [
    "Environments",
    "Services",
    "Deployments",
    "Integrations",
    "Audit trail",
    "Overview",
  ]) {
    await page.getByRole("link", { name, exact: true }).click();
    await expect(page.locator("main.content h1")).toBeVisible();
  }
  await page.screenshot({
    path: "../.local/dashboard-tablet.png",
    fullPage: true,
  });
});
