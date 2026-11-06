import { expect, test, type Page } from "@playwright/test";

/** What the scripted model invents (backend/tests/e2e_app.py). None of it may ever reach the screen. */
const NEVER = ["150 billion", "$150", "economic-overview"];

async function expectNothingRemoved(page: Page) {
  const text = await page.locator("body").innerText();
  for (const phrase of NEVER) expect(text, `"${phrase}" must not be on screen`).not.toContain(phrase);
  const links = await page.locator("a[href]").evaluateAll((all) => all.map((a) => a.getAttribute("href") ?? ""));
  for (const href of links) expect(href).not.toContain("economic-overview");
}

test("the canvas shows lineage, a decision goes through approval, and no removed figure appears", async ({ page }) => {
  const problems: string[] = [];
  page.on("pageerror", (e) => problems.push(e.message));

  await page.goto("/");
  const runway = page.getByTestId("kpi-runway");
  await expect(runway).toContainText(" mo");
  await runway.getByRole("button").first().click();
  const lineage = page.getByRole("dialog", { name: /Lineage of runway/ });
  await expect(lineage).toContainText("Formula");
  await expect(lineage).toContainText(".csv");
  await page.keyboard.press("Escape");

  // Sliders ask the backend again; the UI does not compute.
  const before = await page.getByTestId("scenario-simulator").innerText();
  await page.getByLabel("New hires").fill("5");
  await expect.poll(() => page.getByTestId("scenario-simulator").innerText()).not.toBe(before);
  await expect(page.getByTestId("monte-carlo")).toContainText("Runway P50");
  await expect(page.getByTestId("scenario-simulator")).toContainText("assumption, confirm");

  // A decision: the proposed option leads, costs are labelled, and nothing runs until approved.
  await page.getByLabel("Ask the advisor").fill("Should we open a Dubai office?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("The team is waiting for your approval.")).toBeVisible({ timeout: 30_000 });
  const lead = page.getByTestId("decision-lead");
  await expect(lead).toContainText("Proposed");
  await expect(lead).toContainText("assumption, confirm");
  await expect(page.getByTestId("decision-frame")).toContainText("Goal check");

  await page.getByRole("link", { name: "Review the team" }).click();
  const approval = page.getByTestId("team-approval");
  await expect(approval).toContainText("Approval needed");
  await approval.getByRole("textbox").first().fill("Check the cash impact only.");
  await approval.getByRole("button", { name: "Approve and run" }).click();
  await expect(page.getByTestId("agent-card").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("agent-card").first()).toContainText("Check the cash impact only.");
  await page.getByRole("button", { name: "timeline" }).click();
  await expect(page.getByRole("list", { name: "Timeline" })).toBeVisible();
  await expectNothingRemoved(page);

  await page.getByRole("link", { name: "Workspace", exact: true }).click();
  const answer = page.getByTestId("advisor-answer").first();
  await expect(answer.getByText(/Verified|Not verified/)).toBeVisible({ timeout: 60_000 });
  await expectNothingRemoved(page);
  await expect(answer).not.toContainText("The team is waiting");

  // Settings apply at once: no approval step from here on.
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByLabel("Ask before a team runs").selectOption("never");
  await expect(page.getByLabel("Ask before a team runs")).toHaveValue("never");
  await page.getByRole("link", { name: "Workspace", exact: true }).click();

  // A metric answer is written by code and verified: the badge comes from the backend, with lineage.
  await page.getByLabel("Ask the advisor").fill("What is our runway?");
  await page.getByRole("button", { name: "Send" }).click();
  const metric = page.getByTestId("advisor-answer").nth(1);
  await expect(metric.getByText("Verified", { exact: true })).toBeVisible({ timeout: 30_000 });
  await expect(metric.getByRole("list", { name: "Numbers used" })).toContainText("Runway");
  await expectNothingRemoved(page);

  // The other panels.
  await page.getByRole("link", { name: "Decisions" }).click();
  await expect(page.getByTestId("priority-matrix")).toBeVisible();
  await page.getByLabel("New initiative").fill("Open a partner channel");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByRole("list", { name: "Ranking" })).toContainText("Open a partner channel");
  await expect(page.getByTestId("memo-sheet")).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export .md" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.md$/);
  await expectNothingRemoved(page);

  await page.getByRole("link", { name: "Data", exact: true }).click();
  await expect(page.getByTestId("data-tables")).toContainText("subscriptions");
  await page.getByRole("link", { name: "Vault", exact: true }).click();
  await expect(page.getByTestId("vault-notes")).toBeVisible();
  await expectNothingRemoved(page);

  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(page.getByTestId("privacy-note")).toContainText("privacy filter");
  await expect(page.getByTestId("agent-routes")).toContainText("Market Scout");

  expect(problems).toEqual([]);
});
