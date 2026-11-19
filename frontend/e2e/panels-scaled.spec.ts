import { expect, test } from "@playwright/test";

/**
 * Founder M6 gate D6: on a 2560x1600 screen at 125 % (Edge), dragging a panel edge and double-clicking it did nothing.
 * Same geometry here: 2048x1280 CSS pixels at a device scale of 1.25.
 */
// E2E_CHANNEL=msedge runs it in Edge, the founder's browser, where it is installed.
test.use({
  viewport: { width: 2048, height: 1280 },
  deviceScaleFactor: 1.25,
  ...(process.env.E2E_CHANNEL ? { channel: process.env.E2E_CHANNEL } : {}),
});

test("at 125 % the panel edges drag, reset on double-click, and widths and the agent window survive F5", async ({
  page,
}) => {
  const problems: string[] = [];
  page.on("pageerror", (e) => problems.push(e.message));
  await page.goto("/");
  await page.evaluate(() => {
    window.localStorage.removeItem("founderos.layout.v1");
    window.localStorage.removeItem("founderos.agentwindow.v1");
  });
  await page.reload();

  const advisor = page.getByRole("complementary", { name: "Executive Advisor", exact: true });
  const rail = page.getByRole("complementary", { name: "Agents" });
  const left = page.getByRole("separator", { name: "Advisor panel width" });
  const right = page.getByRole("separator", { name: "Agents panel width" });
  await expect(left).toBeVisible();
  await expect(right).toBeVisible();

  // a hit area of at least 8 px, with the resize cursor
  for (const handle of [left, right]) {
    const box = await handle.boundingBox();
    expect(box?.width ?? 0).toBeGreaterThanOrEqual(8);
    expect(await handle.evaluate((el) => getComputedStyle(el).cursor)).toBe("col-resize");
  }

  // drag where a person would grab it: the middle of the handle, as found by hit-testing (nothing on top of it)
  const drag = async (handle: typeof left, dx: number) => {
    const box = await handle.boundingBox();
    if (!box) throw new Error("no handle");
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    const topmost = await page.evaluate(
      ({ px, py }) => document.elementFromPoint(px, py)?.closest('[role="separator"]')?.getAttribute("aria-label"),
      { px: x, py: y },
    );
    expect(topmost).toBe(await handle.getAttribute("aria-label"));
    await page.mouse.move(x, y);
    await page.mouse.down();
    await page.mouse.move(x + dx / 2, y, { steps: 4 });
    await page.mouse.move(x + dx, y, { steps: 4 });
    await page.mouse.up();
  };

  await drag(left, 150);
  await expect.poll(async () => Math.round((await advisor.boundingBox())?.width ?? 0)).toBe(530);
  await drag(right, -100);
  await expect.poll(async () => Math.round((await rail.boundingBox())?.width ?? 0)).toBe(400);

  // F5 keeps both
  await page.reload();
  await expect.poll(async () => Math.round((await advisor.boundingBox())?.width ?? 0)).toBe(530);
  await expect.poll(async () => Math.round((await rail.boundingBox())?.width ?? 0)).toBe(400);

  // double-click: back to the default
  await left.dblclick();
  await expect.poll(async () => Math.round((await advisor.boundingBox())?.width ?? 0)).toBe(380);
  await right.dblclick();
  await expect.poll(async () => Math.round((await rail.boundingBox())?.width ?? 0)).toBe(300);

  // the agent window comes back where it was left, after F5 and reopening
  await page.getByRole("button", { name: /^Agents/ }).click();
  const win = page.getByRole("dialog", { name: "Agent window" });
  await expect(win).toBeVisible();
  const start = await win.boundingBox();
  if (!start) throw new Error("no window");
  await page.mouse.move(start.x + 60, start.y + 15);
  await page.mouse.down();
  await page.mouse.move(start.x - 340, start.y + 215, { steps: 8 });
  await page.mouse.up();
  const moved = await win.boundingBox();
  await page.reload();
  await page.getByRole("button", { name: /^Agents/ }).click();
  await expect(win).toBeVisible();
  const back = await win.boundingBox();
  expect(Math.round(back?.x ?? 0)).toBe(Math.round(moved?.x ?? -1));
  expect(Math.round(back?.y ?? 0)).toBe(Math.round(moved?.y ?? -1));
  expect(problems).toEqual([]);
});
