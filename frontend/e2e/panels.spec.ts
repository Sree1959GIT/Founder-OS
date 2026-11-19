import { expect, test } from "@playwright/test";

/** Founder decisions F (panels) and G (agent window), M6. Screenshots go to E2E_SHOTS when it is set. */
const shots = process.env.E2E_SHOTS;

test("panels resize, fold and are remembered; the agent window moves and follows the team", async ({ page }) => {
  const problems: string[] = [];
  page.on("pageerror", (e) => problems.push(e.message));
  await page.goto("/");
  await page.evaluate(() => window.localStorage.removeItem("founderos.layout.v1"));
  await page.reload();

  // F: drag the Advisor panel's edge wider
  const advisor = page.getByRole("complementary", { name: "Executive Advisor", exact: true });
  const before = (await advisor.boundingBox())?.width ?? 0;
  expect(Math.round(before)).toBe(380);
  const handle = page.getByRole("separator", { name: "Advisor panel width" });
  const box = await handle.boundingBox();
  if (!box) throw new Error("no handle");
  await page.mouse.move(box.x + box.width / 2, box.y + 200);
  await page.mouse.down();
  await page.mouse.move(box.x + 120, box.y + 200, { steps: 6 });
  await page.mouse.up();
  await expect.poll(async () => Math.round((await advisor.boundingBox())?.width ?? 0)).toBeGreaterThan(470);

  // the right panel with the keyboard
  const rail = page.getByRole("complementary", { name: "Agents" });
  const railBefore = Math.round((await rail.boundingBox())?.width ?? 0);
  await page.getByRole("separator", { name: "Agents panel width" }).focus();
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  await expect.poll(async () => Math.round((await rail.boundingBox())?.width ?? 0)).toBe(railBefore + 32);

  // remembered after a reload
  const wide = Math.round((await advisor.boundingBox())?.width ?? 0);
  await page.reload();
  await expect.poll(async () => Math.round((await advisor.boundingBox())?.width ?? 0)).toBe(wide);

  // fold and unfold
  await page.getByRole("button", { name: "Fold the Advisor panel" }).click();
  await expect(advisor).toBeHidden();
  if (shots) await page.screenshot({ path: `${shots}/f-folded.png` });
  await page.getByRole("button", { name: "Show the Advisor panel" }).click();
  await expect(advisor).toBeVisible();

  // G: the agent window, opened from the Advisor panel
  await page.getByRole("button", { name: /^Agents/ }).click();
  const win = page.getByRole("dialog", { name: "Agent window" });
  await expect(win).toBeVisible();
  await expect(win).toContainText("the agents working on it appear here");
  await page.getByLabel("Ask the advisor").fill("Should we open a Dubai office?");
  await page.getByRole("button", { name: "Send" }).click();
  // the smoke spec may already have set approval to Never in this backend: either the team waits or it works
  const approval = win.getByRole("link", { name: "The team needs your approval" });
  const rows = win.getByTestId("agent-window-row");
  await expect(approval.or(rows.first())).toBeVisible({ timeout: 30_000 });

  // move it by its title bar
  const start = await win.boundingBox();
  if (!start) throw new Error("no window");
  await page.mouse.move(start.x + 60, start.y + 15);
  await page.mouse.down();
  await page.mouse.move(start.x - 240, start.y + 135, { steps: 6 });
  await page.mouse.up();
  const moved = await win.boundingBox();
  expect(Math.round((moved?.x ?? 0) - start.x)).toBe(-300);
  expect(Math.round((moved?.y ?? 0) - start.y)).toBe(120);

  // it stays open on the Activity tab, where the team is approved, and draws each agent
  if (await approval.isVisible()) {
    await approval.click();
    await page.getByTestId("team-approval").getByRole("button", { name: "Approve and run" }).click();
  } else {
    await page.getByRole("link", { name: "Activity" }).first().click();
  }
  await expect(rows.first()).toBeVisible({ timeout: 30_000 });
  await expect(win.getByRole("list", { name: "Where the run is" })).toContainText("Plan");
  if (shots) await page.screenshot({ path: `${shots}/g-window.png` });
  await expect(win.getByRole("list", { name: "Where the run is" }).locator('[data-state="done"]')).toHaveCount(4, {
    timeout: 60_000,
  });
  await page.getByRole("link", { name: "Workspace", exact: true }).click();
  if (shots) await page.screenshot({ path: `${shots}/fg-workspace.png` });
  await page.keyboard.press("Escape");
  await expect(win).toBeHidden();
  expect(problems).toEqual([]);
});
