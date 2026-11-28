import { expect, test, type Page } from "@playwright/test";

/** M7b: Welcome and the Boardroom, desktop 1440 px and phone 390 px. Screenshots go to E2E_SHOTS when it is set. */
const shots = process.env.E2E_SHOTS;

async function noSideScroll(page: Page) {
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(wide, "no sideways page scroll").toBeLessThanOrEqual(1);
}

for (const [name, width, height] of [
  ["desktop", 1440, 900],
  ["phone", 390, 844],
] as const) {
  test(`Welcome, then the Boardroom (${name})`, async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: shots ? 2 : 1, hasTouch: name === "phone" });
    const page = await context.newPage();
    const problems: string[] = [];
    page.on("pageerror", (e) => problems.push(e.message));
    const fontCalls: string[] = [];
    page.on("request", (r) => {
      if (/fonts\.(googleapis|gstatic)\.com/.test(r.url())) fontCalls.push(r.url());
    });
    expect((await page.request.put("/api/settings", { data: { team_approval: "always" } })).ok()).toBe(true);

    await page.goto("/");
    const welcome = page.getByTestId("welcome");
    await expect(welcome.getByRole("heading", { level: 1 })).toHaveText("Ask a hard question. Six AI advisors argue it out. You decide.");
    await expect(welcome).toContainText("They read your own numbers, check each other's work");
    await expect(page.getByTestId("meet-team").getByRole("listitem")).toHaveCount(7);
    await expect(page.getByRole("button", { name: "Should we open a Dubai office?" })).toBeVisible();
    await expect(page.getByTestId("kpi-runway")).toContainText(" mo");
    await page.waitForTimeout(400); // fonts settle
    await noSideScroll(page);
    if (shots) await page.screenshot({ path: `${shots}/m7b-welcome-${name}.png` });

    await page.getByLabel("What are you deciding?").fill("Should we open a Dubai office?");
    await page.getByRole("button", { name: /Call the team/ }).click();
    await expect(page.getByTestId("boardroom")).toBeVisible();
    const options = page.getByTestId(name === "phone" ? "options-phone" : "options-panel");
    await expect(options.getByTestId("option-leading")).toBeVisible({ timeout: 30_000 });
    await expect(options.getByTestId("option-leading")).toContainText("Leading");
    if (name === "desktop") {
      await expect(page.getByTestId("boardroom-table")).toContainText("Dubai office");
      await expect(page.getByTestId("caption-bar")).toContainText("LIVE");
      await expect(page.getByTestId("boardroom-table").getByTestId("seat").first()).toContainText("Advisor");
    } else {
      await expect(page.getByTestId("phone-stage")).toContainText("Dubai office");
      await expect(page.getByTestId("phone-bar")).toContainText("Accept");
      await expect(page.getByTestId("phone-bar").getByRole("button", { name: /Hold to talk|Talk/ })).toBeVisible();
    }
    await page.waitForTimeout(600);
    await noSideScroll(page);
    if (shots) await page.screenshot({ path: `${shots}/m7b-boardroom-${name}.png` });
    expect(fontCalls).toEqual([]);
    expect(problems).toEqual([]);
    await context.close();
  });
}
