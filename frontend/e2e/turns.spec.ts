import { expect, test } from "@playwright/test";

// Founder re-test RW6 (22) and 42: a turn is taken at once in every phase, and the same question is queued once.
test("turns are accepted while the first question is planning and while it waits for approval", async ({ page }) => {
  await page.goto("/");
  const ask = page.getByLabel("Ask the advisor");

  await ask.fill("Should we open a Dubai office?");
  await ask.press("Enter");
  // Straight away, while it is still being planned.
  await ask.fill("What is our runway?");
  await ask.press("Enter");
  await expect(ask).toHaveValue("");
  const queued = page.getByTestId("queued");
  await expect(queued.filter({ hasText: "What is our runway?" })).toBeVisible({ timeout: 10_000 });

  // While it waits for the founder's approval.
  await expect(page.getByText("The team is waiting for your approval.")).toBeVisible({ timeout: 30_000 });
  await ask.fill("What is our churn?");
  await ask.press("Enter");
  await expect(queued.filter({ hasText: "What is our churn?" })).toBeVisible({ timeout: 10_000 });

  // The same question again, in other case and spacing: still one card.
  await ask.fill("what is our  RUNWAY?");
  await ask.press("Enter");
  await expect(page.getByText("That question is already queued.")).toBeVisible({ timeout: 10_000 });
  await expect(queued).toHaveCount(2);
});
