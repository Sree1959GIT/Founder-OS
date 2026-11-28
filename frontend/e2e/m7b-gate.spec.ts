import { expect, test, type Page } from "@playwright/test";

/**
 * M7b founder gate fixes (F20–F27) in a real browser. Screenshots go to E2E_SHOTS when it is set:
 * gate-*-desktop (1440 px), gate-*-phone (390 px), the narrow centre (F26) and long numbers (F20).
 */
const shots = process.env.E2E_SHOTS;
const shot = async (page: Page, name: string) => {
  if (shots) await page.screenshot({ path: `${shots}/${name}.png` });
};

async function noSideScroll(page: Page) {
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(wide, "no sideways page scroll").toBeLessThanOrEqual(1);
}

async function askDubai(page: Page) {
  expect((await page.request.put("/api/settings", { data: { team_approval: "never" } })).ok()).toBe(true);
  await page.goto("/");
  await page.getByLabel("What are you deciding?").fill("Should we open a Dubai office?");
  await page.getByRole("button", { name: /Call the team/ }).click();
  await expect(page.getByTestId("boardroom")).toBeVisible();
}

test("F25 F27 F24 F21: the adaptive table, voice on the faces, the topic, one status (desktop)", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: shots ? 2 : 1 });
  const page = await context.newPage();
  await askDubai(page);
  const table = page.getByTestId("boardroom-table");
  await expect(page.getByTestId("table-topic").first()).toHaveText("Dubai office");
  await expect(page.getByTestId("options-panel").getByTestId("option-leading")).toBeVisible({ timeout: 30_000 });
  const seats = Number(await table.getAttribute("data-seats"));
  expect(seats).toBeGreaterThanOrEqual(3); // the host plus the team the planner chose (2 to 8)
  expect(seats).toBeLessThanOrEqual(9);
  await expect(table.getByTestId("seat")).toHaveCount(seats);
  await expect(table.getByRole("button", { name: /^Talk to / })).toHaveCount(seats);
  await expect(page.getByText("Start voice")).toHaveCount(0);
  await expect(page.getByTestId("talking-to")).toHaveText("Tap a face to talk");
  await expect(page.getByTestId("system-status")).toHaveText(/All systems OK|Slow right now/);
  await expect(page.getByText("Ollama")).toHaveCount(0);
  // seats never overlap each other
  const boxes = await table.getByTestId("seat-face").evaluateAll((els) => els.map((e) => e.getBoundingClientRect().toJSON()));
  for (let i = 0; i < boxes.length; i += 1)
    for (let j = i + 1; j < boxes.length; j += 1) {
      const a = boxes[i];
      const b = boxes[j];
      const apart = a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top;
      expect(apart, `seat ${i} and ${j} overlap`).toBe(true);
    }
  await page.waitForTimeout(500);
  await noSideScroll(page);
  await shot(page, "gate-boardroom-desktop");

  // F26: Focus on the team folds both panels; the table stays.
  await page.getByTestId("focus-team").click();
  await expect(page.getByTestId("options-folded")).toBeVisible();
  await expect(page.getByRole("button", { name: "Show the Advisor panel" })).toBeVisible();
  await expect(table).toBeVisible();
  await shot(page, "gate-focus-desktop");
  await page.getByTestId("focus-team").click();
  await expect(page.getByTestId("options-panel")).toBeVisible();

  // F22: a reload opens on Welcome, with one line to continue.
  await page.reload();
  await expect(page.getByTestId("welcome")).toBeVisible();
  await expect(page.getByTestId("open-decision")).toContainText("You have an open decision: Dubai office.");
  await page.waitForTimeout(700); // the headline's rise has finished
  await shot(page, "gate-welcome-open-decision-desktop");
  await page.getByRole("link", { name: /Continue it/ }).click();
  await expect(page.getByTestId("boardroom")).toBeVisible();
  await expect(page.getByTestId("earlier-turns").first()).toBeVisible();
  await context.close();
});

test("F26: a narrow centre switches to the phone-style stage; nothing overlaps", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1180, height: 860 }, deviceScaleFactor: shots ? 2 : 1 });
  await context.addInitScript(() => {
    window.localStorage.setItem("founderos.layout.v1", JSON.stringify({ left: 720, right: 560, leftCollapsed: false, rightCollapsed: false }));
  });
  const page = await context.newPage();
  await askDubai(page);
  const centre = page.getByTestId("boardroom");
  await expect(centre).toHaveAttribute("data-compact", "true");
  expect((await centre.boundingBox())?.width ?? 0).toBeGreaterThanOrEqual(540); // the centre keeps its minimum (+/- padding)
  await expect(page.getByTestId("phone-stage")).toBeVisible();
  await expect(page.getByTestId("boardroom-table")).toHaveCount(0);
  await expect(page.getByTestId("options-panel").getByTestId("option-leading")).toBeVisible({ timeout: 30_000 });
  // the right panel has its own handle now
  await expect(page.getByRole("separator", { name: "Options panel width" })).toBeVisible();
  await page.waitForTimeout(500);
  await noSideScroll(page);
  await shot(page, "gate-narrow-centre");
  await context.close();
});

for (const [name, width, height] of [
  ["desktop", 1440, 900],
  ["phone", 390, 844],
] as const) {
  test(`F20: long figures are never cut off (${name})`, async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: shots ? 2 : 1, hasTouch: name === "phone" });
    const page = await context.newPage();
    const lineage = { sql: ["SELECT 1"], source_files: ["finance.csv"], source_rows: [], formula: "sum", inputs: {}, period: "2026-10", computed_at: "2026-11-27T10:00:00Z" };
    const big = (metric: string, label: string, value: number, unit: string) => ({
      metric,
      label,
      value,
      unit,
      as_of: "2026-10-31",
      note: null,
      detail: null,
      lineage: { ...lineage, metric },
    });
    await page.route("**/api/metrics/summary", (route) =>
      route.fulfill({
        json: {
          metrics: [
            big("gross_margin", "Gross margin", 0.6421, "ratio"),
            big("net_burn", "Net burn", 1255344.99, "USD"),
            big("mrr", "MRR", 98765432.1, "USD"),
            big("runway", "Runway", 14.2, "months"),
          ],
          unavailable: {},
        },
      }),
    );
    await page.goto("/");
    const row = page.getByTestId("kpi-row");
    await expect(row).toBeVisible();
    const figures = row.getByTestId("figure");
    await expect(figures).toHaveCount(4);
    for (const fig of await figures.all()) {
      const fits = await fig.evaluate((el) => el.scrollWidth <= el.clientWidth + 1 && !getComputedStyle(el).textOverflow.includes("ellipsis"));
      expect(fits, `${await fig.textContent()} is cut off`).toBe(true);
      await expect(fig).not.toContainText("…");
    }
    await noSideScroll(page);
    await row.scrollIntoViewIfNeeded();
    await shot(page, `gate-long-numbers-${name}`);
    await context.close();
  });
}

test("phone: the strip of faces, tappable, and the plain status (390 px)", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: shots ? 2 : 1, hasTouch: true });
  const page = await context.newPage();
  await askDubai(page);
  const stage = page.getByTestId("phone-stage");
  await expect(stage.getByTestId("table-topic")).toHaveText("Dubai office");
  await expect(stage.getByRole("button", { name: /^Talk to / }).first()).toBeVisible();
  await expect(page.getByTestId("options-phone").getByTestId("option-leading")).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(500);
  await noSideScroll(page);
  await shot(page, "gate-boardroom-phone");
  await context.close();
});
